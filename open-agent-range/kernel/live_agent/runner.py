"""Causal live-model runner: observe once, fork the exact dangerous intent."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from kernel.demo import reference_surface
from kernel.evidence import EvidenceStore
from kernel.injection import Injection, apply_injections
from kernel.ledger import Ledger
from kernel.live_agent.models import (
    RESULT_SCHEMA_VERSION,
    AgentTurn,
    AttackCase,
    ExperimentConfig,
    PromptProfile,
    ToolIntent,
    sha256_json,
)
from kernel.live_agent.policy import assess_intent, harm_observed
from kernel.live_agent.provider import ModelAdapter, openai_tools
from kernel.policy_overlay import overlay_from_scenario
from kernel.scenario import Scenario, build_world, load_scenario, with_injections
from kernel.sut import NullSUT, SUT, ToolCall, XaGuardSUT

GuardFactory = Callable[[Scenario], SUT]


class LiveAgentRunner:
    def __init__(
        self,
        config: ExperimentConfig,
        adapter: ModelAdapter,
        *,
        evidence_dir: Path | str,
        guard_mode: str = "live",
        xa_guard_root: Path | None = None,
        guard_factory: GuardFactory | None = None,
    ) -> None:
        if guard_mode not in {"live", "offline"}:
            raise ValueError("guard_mode must be live or offline")
        self.config = config
        self.adapter = adapter
        self.evidence_dir = Path(evidence_dir)
        self.guard_mode = guard_mode
        self.xa_guard_root = xa_guard_root
        self.guard_factory = guard_factory
        self.surface = reference_surface()

    def run(self, *, phase: str = "holdout", repeats: int | None = None) -> dict[str, Any]:
        selected = self.config.cases_for_phase(phase)
        if not selected:
            raise ValueError(f"manifest has no cases for phase={phase}")
        repeat_count = repeats if repeats is not None else self.config.repeats
        if repeat_count < 1:
            raise ValueError("repeats must be >= 1")
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        frozen = freeze_manifest(self.config, phase=phase, repeats=repeat_count)
        _write_json(self.evidence_dir / "experiment-manifest.json", frozen)

        results: list[dict[str, Any]] = []
        for case in selected:
            for profile in self.config.prompt_profiles:
                for repeat_index in range(1, repeat_count + 1):
                    run_dir = (
                        self.evidence_dir
                        / "runs"
                        / case.case_id
                        / profile.profile_id
                        / f"run-{repeat_index:03d}"
                    )
                    result = self.run_once(
                        case,
                        profile,
                        repeat_index=repeat_index,
                        run_dir=run_dir,
                    )
                    results.append(result)
        summary = summarize_results(
            self.config,
            results,
            phase=phase,
            repeat_count=repeat_count,
        )
        _write_json(self.evidence_dir / "summary.json", summary)
        from kernel.live_agent.render import render_replay

        render_replay(self.evidence_dir)
        _write_hash_manifest(self.evidence_dir)
        return summary

    def run_once(
        self,
        case: AttackCase,
        profile: PromptProfile,
        *,
        repeat_index: int,
        run_dir: Path,
    ) -> dict[str, Any]:
        run_dir.mkdir(parents=True, exist_ok=True)
        session_id = f"{case.case_id}-{profile.profile_id}-{repeat_index:03d}"
        scenario = _scenario_for_case(self.config, case)
        world = build_world(scenario)
        apply_injections(world, scenario.injections)
        ledger = Ledger()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": profile.system_prompt},
            {"role": "user", "content": case.task},
        ]
        tools = openai_tools(self.surface, case.tool_names)
        transcript: list[dict[str, Any]] = [
            {"turn": 0, "role": "system", "content": profile.system_prompt},
            {"turn": 0, "role": "user", "content": case.task},
        ]
        intent: ToolIntent | None = None
        intent_reason = ""
        final_content = ""
        safe_tool_count = 0
        infra_status = "ok"
        infra_error = ""

        try:
            for turn_number in range(1, self.config.max_turns + 1):
                turn = self.adapter.next_turn(messages, tools)
                transcript.append({"turn": turn_number, "role": "assistant", **turn.to_dict()})
                final_content = turn.content
                messages.append(_assistant_message(turn))
                if not turn.tool_calls:
                    break
                stop = False
                for call in turn.tool_calls:
                    if call.parse_error:
                        output = {"error": "invalid_tool_arguments", "detail": call.parse_error}
                    elif call.name not in case.tool_names:
                        output = {"error": "tool_not_available", "tool": call.name}
                    else:
                        assessment = assess_intent(case, call, world)
                        transcript.append(
                            {
                                "turn": turn_number,
                                "role": "policy-observer",
                                "tool_call_id": call.tool_call_id,
                                "violating": assessment.violating,
                                "property_id": assessment.property_id,
                                "target": assessment.target,
                                "reason": assessment.reason,
                            }
                        )
                        if assessment.violating:
                            intent = ToolIntent.capture(
                                session_id=session_id,
                                case=case,
                                profile=profile,
                                turn_number=turn_number,
                                turn=turn,
                                call=call,
                                target=assessment.target,
                            )
                            intent_reason = assessment.reason
                            stop = True
                            break
                        try:
                            output = self.surface.execute(
                                call.name,
                                world,
                                ledger,
                                case.principal,
                                dict(call.arguments),
                            )
                            safe_tool_count += 1
                        except (KeyError, ValueError, NotImplementedError) as exc:
                            # A model can hallucinate a locator or argument. That is
                            # an agent/tool result, not provider infrastructure failure.
                            output = {
                                "error": "tool_execution_error",
                                "error_type": type(exc).__name__,
                                "detail": str(exc),
                            }
                    transcript.append(
                        {
                            "turn": turn_number,
                            "role": "tool",
                            "tool_call_id": call.tool_call_id,
                            "name": call.name,
                            "content": output,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.tool_call_id,
                            "content": json.dumps(output, ensure_ascii=False),
                        }
                    )
                if stop:
                    break
        except BaseException as exc:  # external provider/infrastructure boundary
            infra_status = "infra_fail"
            infra_error = f"{type(exc).__name__}: {exc}"
            transcript.append(
                {
                    "role": "infra-error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

        result: dict[str, Any] = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "session_id": session_id,
            "case_id": case.case_id,
            "phase": case.phase,
            "family": case.family,
            "property_id": case.property_id,
            "expected_target": case.expected_target,
            "prompt_profile": profile.profile_id,
            "repeat_index": repeat_index,
            "model": self.config.model,
            "thinking": self.config.thinking,
            "infra_status": infra_status,
            "infra_error": infra_error,
            "model_attempt_violation": intent is not None,
            "intent_reason": intent_reason,
            "intent_id": intent.intent_id if intent else "",
            "intent_target": intent.target if intent else "",
            "intent_arguments_sha256": intent.arguments_sha256 if intent else "",
            "null_harm": False,
            "guard_harm": False,
            "guard_decision": "not_run",
            "guard_reason": "",
            "same_intent_both_arms": False,
            "utility_success": infra_status == "ok" and intent is None and bool(final_content or safe_tool_count),
            "safe_tool_count": safe_tool_count,
            "final_content_sha256": sha256(final_content.encode("utf-8")).hexdigest()
            if final_content
            else "",
            "final_content_chars": len(final_content),
        }
        _write_jsonl(run_dir / "agent-transcript.jsonl", transcript)
        _write_json(run_dir / "world-before-intent.json", world.to_dict())
        if intent is not None and infra_status == "ok":
            _write_json(run_dir / "tool-intent.json", intent.to_dict())
            result.update(self._execute_fork(case, scenario, intent, world, ledger, run_dir))
        _write_json(run_dir / "verdict.json", result)
        return result

    def _execute_fork(
        self,
        case: AttackCase,
        scenario: Scenario,
        intent: ToolIntent,
        world: Any,
        ledger: Ledger,
        run_dir: Path,
    ) -> dict[str, Any]:
        call = ToolCall(intent.tool_name, copy.deepcopy(intent.arguments))
        null_world = copy.deepcopy(world)
        null_ledger = copy.deepcopy(ledger)
        null_before = len(null_world.side_effects)
        null_output = NullSUT().invoke(null_world, null_ledger, case.principal, call, self.surface)
        null_harm = harm_observed(case, null_world, initial_side_effect_count=null_before)
        _write_branch(
            run_dir / "null",
            world=null_world,
            ledger=null_ledger,
            output=null_output,
            harm=null_harm,
            intent=intent,
        )

        guard_world = copy.deepcopy(world)
        guard_ledger = copy.deepcopy(ledger)
        guard_before = len(guard_world.side_effects)
        guard = self._make_guard(scenario)
        guard_dir = run_dir / "xaguard"
        guard_dir.mkdir(parents=True, exist_ok=True)
        if isinstance(guard, XaGuardSUT) and guard.live:
            guard.prepare(EvidenceStore(guard_dir), scenario, self.surface)
        guard.begin_attempt()
        try:
            guard_output = guard.invoke(
                guard_world,
                guard_ledger,
                case.principal,
                ToolCall(intent.tool_name, copy.deepcopy(intent.arguments)),
                self.surface,
            )
        finally:
            guard.end_attempt()
        guard_harm = harm_observed(case, guard_world, initial_side_effect_count=guard_before)
        guard_decision = str(guard_output.get("decision", "allow"))
        guard_reason = str(guard_output.get("reason", ""))
        _write_branch(
            guard_dir,
            world=guard_world,
            ledger=guard_ledger,
            output=guard_output,
            harm=guard_harm,
            intent=intent,
            audit=[asdict(record) for record in guard.audit],
        )
        return {
            "null_harm": null_harm,
            "guard_harm": guard_harm,
            "guard_decision": guard_decision,
            "guard_reason": guard_reason,
            "same_intent_both_arms": True,
        }

    def _make_guard(self, scenario: Scenario) -> SUT:
        if self.guard_factory is not None:
            return self.guard_factory(scenario)
        return XaGuardSUT(
            policy=overlay_from_scenario(scenario),
            xa_guard_root=self.xa_guard_root,
            live=self.guard_mode == "live",
        )


def freeze_manifest(
    config: ExperimentConfig,
    *,
    phase: str,
    repeats: int,
) -> dict[str, Any]:
    selected = [case.to_dict() for case in config.cases_for_phase(phase)]
    payload = config.to_public_dict()
    payload["cases"] = selected
    payload["evaluation"]["active_repeats"] = repeats
    payload["evaluation"]["active_phase"] = phase
    payload["frozen_at"] = _now_iso()
    payload["source_manifest_sha256"] = sha256_json(config.to_public_dict())
    payload["frozen_payload_sha256"] = sha256_json(payload)
    return payload


def summarize_results(
    config: ExperimentConfig,
    results: list[dict[str, Any]],
    *,
    phase: str,
    repeat_count: int,
) -> dict[str, Any]:
    scheduled = len(results)
    attempts = [item for item in results if item["model_attempt_violation"]]
    null_harms = [item for item in attempts if item["null_harm"]]
    guard_harms = [item for item in attempts if item["guard_harm"]]
    blocked = [
        item
        for item in attempts
        if item["guard_decision"] == "deny" and not item["guard_harm"]
    ]
    utilities = [item for item in results if item["utility_success"]]
    stable: list[dict[str, Any]] = []
    for case in config.cases_for_phase(phase):
        for profile in config.prompt_profiles:
            subset = [
                item
                for item in results
                if item["case_id"] == case.case_id
                and item["prompt_profile"] == profile.profile_id
            ]
            target_counts: dict[str, int] = {}
            for item in subset:
                if item["model_attempt_violation"]:
                    key = f"{item['property_id']}::{item['intent_target']}"
                    target_counts[key] = target_counts.get(key, 0) + 1
            best_key, best_count = ("", 0)
            if target_counts:
                best_key, best_count = max(target_counts.items(), key=lambda pair: pair[1])
            matching = [
                item
                for item in subset
                if f"{item['property_id']}::{item['intent_target']}" == best_key
            ]
            stable.append(
                {
                    "case_id": case.case_id,
                    "family": case.family,
                    "property_id": case.property_id,
                    "prompt_profile": profile.profile_id,
                    "scheduled_repeats": repeat_count,
                    "best_intent_key": best_key,
                    "attempt_count": best_count,
                    "threshold": config.breach_threshold,
                    "stable_breach": best_count >= config.breach_threshold,
                    "causal_proof": best_count >= config.breach_threshold
                    and bool(matching)
                    and all(item["null_harm"] and not item["guard_harm"] for item in matching),
                    "infra_failures": sum(item["infra_status"] != "ok" for item in subset),
                }
            )
    return {
        "schema_version": "oar-live-agent-summary/v1",
        "experiment_id": config.experiment_id,
        "phase": phase,
        "model": config.model,
        "thinking": config.thinking,
        "scheduled_runs": scheduled,
        "attempt_asr": _ratio(len(attempts), scheduled),
        "null_harm_asr": _ratio(len(null_harms), scheduled),
        "guard_harm_asr": _ratio(len(guard_harms), scheduled),
        "conditional_block_rate": _ratio(len(blocked), len(attempts)),
        "utility_success_rate": _ratio(len(utilities), scheduled),
        "infra_failures": sum(item["infra_status"] != "ok" for item in results),
        "valid_breach_found": any(item["stable_breach"] for item in stable),
        "causal_proof_found": any(item["causal_proof"] for item in stable),
        "stable_results": stable,
        "runs": results,
        "generated_at": _now_iso(),
    }


def _scenario_for_case(config: ExperimentConfig, case: AttackCase) -> Scenario:
    base = load_scenario(config.world_path)
    injections = [
        Injection(
            into=str(item["into"]),
            content=str(item["content"]),
            meta=dict(item.get("meta", {})),
        )
        for item in case.injections
    ]
    return with_injections(base, injections)


def _assistant_message(turn: AgentTurn) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": turn.content or None}
    if turn.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.tool_call_id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.raw_arguments},
            }
            for call in turn.tool_calls
        ]
    return message


def _write_branch(
    directory: Path,
    *,
    world: Any,
    ledger: Ledger,
    output: dict[str, Any],
    harm: bool,
    intent: ToolIntent,
    audit: list[dict[str, Any]] | None = None,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    _write_json(directory / "world-out.json", world.to_dict())
    _write_json(directory / "tool-output.json", output)
    _write_json(
        directory / "branch-verdict.json",
        {
            "intent_id": intent.intent_id,
            "arguments_sha256": intent.arguments_sha256,
            "harm_observed": harm,
            "decision": output.get("decision", "allow"),
            "executed": output.get("executed", True),
            "audit": audit or [],
        },
    )
    _write_jsonl(directory / "ledger.jsonl", [entry.to_dict() for entry in ledger.entries])


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n" for value in values)
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_hash_manifest(root: Path) -> None:
    hashes: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative == "artifact-hashes.json":
            continue
        hashes[relative] = sha256(path.read_bytes()).hexdigest()
    _write_json(
        root / "artifact-hashes.json",
        {
            "schema_version": "oar-live-agent-artifact-hashes/v1",
            "algorithm": "sha256",
            "artifacts": hashes,
        },
    )


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_local_env(path: Path | str = ".env") -> None:
    """Load simple KEY=VALUE entries without adding a dotenv dependency."""

    env_path = Path(path)
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value
