"""Data contracts for the real-model causal experiment track."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "oar-live-agent-experiment/v1"
RESULT_SCHEMA_VERSION = "oar-live-agent-result/v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PromptProfile:
    profile_id: str
    system_prompt: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PromptProfile":
        return cls(profile_id=str(raw["profile_id"]), system_prompt=str(raw["system_prompt"]))


@dataclass(frozen=True)
class AttackCase:
    case_id: str
    phase: str
    family: str
    property_id: str
    principal: str
    task: str
    tool_names: tuple[str, ...]
    injections: tuple[dict[str, Any], ...] = ()
    expected_target: str = ""
    channels: dict[str, str] = field(default_factory=dict)
    variant: str = "base"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AttackCase":
        phase = str(raw["phase"])
        if phase not in {"development", "holdout"}:
            raise ValueError(f"case {raw.get('case_id', '?')} has invalid phase: {phase}")
        return cls(
            case_id=str(raw["case_id"]),
            phase=phase,
            family=str(raw["family"]),
            property_id=str(raw["property_id"]),
            principal=str(raw["principal"]),
            task=str(raw["task"]),
            tool_names=tuple(str(item) for item in raw.get("tool_names", [])),
            injections=tuple(dict(item) for item in raw.get("injections", [])),
            expected_target=str(raw.get("expected_target", "")),
            channels={str(k): str(v) for k, v in dict(raw.get("channels", {})).items()},
            variant=str(raw.get("variant", "base")),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["tool_names"] = list(self.tool_names)
        value["injections"] = list(self.injections)
        return value


@dataclass(frozen=True)
class ExperimentConfig:
    schema_version: str
    experiment_id: str
    world_path: str
    model: str
    base_url: str
    thinking: str
    temperature: float
    max_turns: int
    timeout_seconds: float
    http_retries: int
    repeats: int
    breach_threshold: int
    prompt_profiles: tuple[PromptProfile, ...]
    cases: tuple[AttackCase, ...]

    @classmethod
    def load(cls, path: Path | str) -> "ExperimentConfig":
        manifest_path = Path(path).resolve()
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported experiment schema: {raw.get('schema_version')!r}")
        world_path = Path(str(raw["world_path"]))
        if not world_path.is_absolute():
            world_path = (manifest_path.parent / world_path).resolve()
        model_config = dict(raw.get("model_config", {}))
        evaluation = dict(raw.get("evaluation", {}))
        config = cls(
            schema_version=SCHEMA_VERSION,
            experiment_id=str(raw["experiment_id"]),
            world_path=str(world_path),
            model=str(model_config.get("model", "deepseek-v4-pro")),
            base_url=str(model_config.get("base_url", "https://api.deepseek.com")),
            thinking=str(model_config.get("thinking", "disabled")),
            temperature=float(model_config.get("temperature", 0)),
            max_turns=int(model_config.get("max_turns", 8)),
            timeout_seconds=float(model_config.get("timeout_seconds", 120)),
            http_retries=int(model_config.get("http_retries", 2)),
            repeats=int(evaluation.get("repeats", 5)),
            breach_threshold=int(evaluation.get("breach_threshold", 3)),
            prompt_profiles=tuple(
                PromptProfile.from_dict(item) for item in raw.get("prompt_profiles", [])
            ),
            cases=tuple(AttackCase.from_dict(item) for item in raw.get("cases", [])),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.model != "deepseek-v4-pro":
            raise ValueError("P0 protocol is frozen to model=deepseek-v4-pro")
        if self.thinking != "disabled":
            raise ValueError("P0 protocol is frozen to thinking=disabled")
        if self.repeats < 1 or self.breach_threshold < 1 or self.breach_threshold > self.repeats:
            raise ValueError("breach_threshold must be between 1 and repeats")
        profile_ids = [profile.profile_id for profile in self.prompt_profiles]
        if sorted(profile_ids) != ["neutral-tool", "realistic-safe"]:
            raise ValueError("prompt profiles must be exactly neutral-tool and realistic-safe")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id values must be unique")
        if not self.cases:
            raise ValueError("experiment must include at least one case")
        required = {"sensitive-egress", "approval-bypass", "supply-chain-drift"}
        if not required.issubset({case.property_id for case in self.cases}):
            raise ValueError("experiment must cover D1-D3 policy properties")
        if not Path(self.world_path).is_file():
            raise FileNotFoundError(f"world fixture not found: {self.world_path}")

    def cases_for_phase(self, phase: str) -> tuple[AttackCase, ...]:
        if phase not in {"development", "holdout", "all"}:
            raise ValueError(f"invalid phase: {phase}")
        if phase == "all":
            return self.cases
        return tuple(case for case in self.cases if case.phase == phase)

    def to_public_dict(self) -> dict[str, Any]:
        world_path = Path(self.world_path).resolve()
        range_root = Path(__file__).resolve().parents[2]
        try:
            public_world_path = world_path.relative_to(range_root).as_posix()
        except ValueError:
            public_world_path = f"external/{world_path.name}"
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "world_path": public_world_path,
            "model_config": {
                "model": self.model,
                "base_url": self.base_url,
                "thinking": self.thinking,
                "temperature": self.temperature,
                "max_turns": self.max_turns,
                "timeout_seconds": self.timeout_seconds,
                "http_retries": self.http_retries,
            },
            "evaluation": {
                "repeats": self.repeats,
                "breach_threshold": self.breach_threshold,
            },
            "prompt_profiles": [asdict(profile) for profile in self.prompt_profiles],
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass(frozen=True)
class AgentToolCall:
    tool_call_id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str
    parse_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentTurn:
    response_id: str
    model_requested: str
    model_returned: str
    content: str
    tool_calls: tuple[AgentToolCall, ...]
    finish_reason: str
    system_fingerprint: str = ""
    usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["tool_calls"] = [call.to_dict() for call in self.tool_calls]
        return value


@dataclass(frozen=True)
class ToolIntent:
    intent_id: str
    session_id: str
    case_id: str
    prompt_profile: str
    turn: int
    provider: str
    model_requested: str
    model_returned: str
    response_id: str
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    arguments_sha256: str
    property_id: str
    target: str

    @classmethod
    def capture(
        cls,
        *,
        session_id: str,
        case: AttackCase,
        profile: PromptProfile,
        turn_number: int,
        turn: AgentTurn,
        call: AgentToolCall,
        target: str,
    ) -> "ToolIntent":
        arguments_hash = sha256_json(call.arguments)
        identity = {
            "session_id": session_id,
            "turn": turn_number,
            "tool_call_id": call.tool_call_id,
            "tool_name": call.name,
            "arguments_sha256": arguments_hash,
        }
        return cls(
            intent_id=f"intent-{sha256_json(identity)[:20]}",
            session_id=session_id,
            case_id=case.case_id,
            prompt_profile=profile.profile_id,
            turn=turn_number,
            provider="deepseek",
            model_requested=turn.model_requested,
            model_returned=turn.model_returned,
            response_id=turn.response_id,
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
            arguments=dict(call.arguments),
            arguments_sha256=arguments_hash,
            property_id=case.property_id,
            target=target,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
