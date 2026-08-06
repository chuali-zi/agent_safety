"""SEALED REPLAY：从封存证据包的真实 artifact 推导 Workbench 事件流。

诚实映射纪律（contracts.md §3/§4）：
- hash 一律直接来自 artifact 文件字节或 artifact 内字段，不重新"预测"。
- audit.jsonl 没有逐 Gate 字段，只能得到 final decision/reason/faithfulness：
  * 决定 Gate：从 gen_ai.decision.final_reason 的 `gateN_*` 前缀解析（如 gate3_policy → GATE3）。
  * 决定 Gate 之前：UNKNOWN（audit 未记录逐 Gate 结果，不渲染为"安全通过"）。
  * 决定 Gate 之后（deny 终止）：NOT_REACHED。
  * GATE5：无 sandbox 工件一律 NOT_REACHED。
  * GATE6：存在带 record_hash 的 audit 记录 → ALLOW（已落链，展示 record_hash）。
- 无 audit 时所有 Gate 显示 UNKNOWN/NOT_REACHED，不声称各 Gate 已通过。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from .events import EventBuilder, artifact_ref, sha256_file

GATE_IDS = ("GATE1", "GATE2", "GATE3", "GATE4", "GATE5", "GATE6")
_GATE_REASON_RE = re.compile(r"gate([1-6])[_\s:]", re.IGNORECASE)
_RUN_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _side_effect_delta(before_path: Path, out_path: Path) -> int:
    """真实 downstream 计数：world 副作用条数差值（来自 artifact，不预测）。"""
    before = _read_json(before_path)
    after = _read_json(out_path)
    before_effects = before.get("side_effects")
    after_effects = after.get("side_effects")
    if not isinstance(before_effects, list) or not isinstance(after_effects, list):
        raise ValueError("world artifact does not contain a side_effects list")
    return max(0, len(after_effects) - len(before_effects))


def deciding_gate_from_reason(reason: str) -> int | None:
    match = _GATE_REASON_RE.search(reason or "")
    return int(match.group(1)) if match else None


def gate_rail_from_audit(
    audit_rows: list[dict[str, Any]],
    branch_verdict: dict[str, Any],
) -> list[dict[str, Any]]:
    """按诚实映射规则从真实 audit 推导六格 Gate 状态。"""
    gates = [{"gate_id": gate_id, "status": "UNKNOWN"} for gate_id in GATE_IDS]
    # GATE5：当前所有证据包均无 sandbox 工件
    gates[4] = {"gate_id": "GATE5", "status": "NOT_REACHED"}
    if not audit_rows:
        return gates

    latest = audit_rows[-1]
    decision = str(latest.get("gen_ai.decision.final", ""))
    reason = str(latest.get("gen_ai.decision.final_reason", ""))
    record_hash = str(latest.get("record_hash", ""))
    hit_ids = [str(item) for item in latest.get("gen_ai.policy.hit_id", []) or []]
    faithfulness = latest.get("gen_ai.decision.faithfulness_score")

    if record_hash and re.fullmatch(r"[a-f0-9]{64}", record_hash):
        gates[5] = {"gate_id": "GATE6", "status": "ALLOW", "audit_record_hash": record_hash}

    deciding = deciding_gate_from_reason(reason)
    if decision == "deny" and deciding is not None:
        gate_event: dict[str, Any] = {"gate_id": f"GATE{deciding}", "status": "DENY"}
        if hit_ids:
            gate_event["rule_ids"] = hit_ids
        if record_hash and re.fullmatch(r"[a-f0-9]{64}", record_hash):
            gate_event["audit_record_hash"] = record_hash
        if isinstance(faithfulness, (int, float)):
            gate_event["faithfulness_score"] = float(faithfulness)
        gates[deciding - 1] = gate_event
        for index in range(deciding, 5):  # 决定 Gate 之后到 GATE5：NOT_REACHED
            gates[index] = {"gate_id": f"GATE{index + 1}", "status": "NOT_REACHED"}
    elif decision == "allow":
        executed = bool(branch_verdict.get("executed"))
        warn_gate = deciding_gate_from_reason(reason) if "warn" in reason.lower() else None
        for index in range(4):
            if warn_gate is not None and index == warn_gate - 1:
                gate_event = {"gate_id": f"GATE{warn_gate}", "status": "WARN"}
                if hit_ids:
                    gate_event["rule_ids"] = hit_ids
                gates[index] = gate_event
            else:
                gates[index] = {"gate_id": f"GATE{index + 1}", "status": "UNKNOWN"}
        if executed:
            gates[4] = {"gate_id": "GATE5", "status": "NOT_REACHED"}
    elif decision in {"pending", "require_approval"}:
        gates[1] = {"gate_id": "GATE2", "status": "REQUIRE_APPROVAL"}
        gates[2] = {"gate_id": "GATE3", "status": "NOT_REACHED"}
        gates[3] = {"gate_id": "GATE4", "status": "NOT_REACHED"}
    return gates


def resolve_run_dir(pack_root: Path, case_id: str, profile_id: str, run_name: str) -> Path:
    """安全解析封存 run，兼容带/不带 profile 的两种布局。

    scenario_id 来自 HTTP 请求，三个组件必须是单一文件名，最终解析结果也必须仍位于
    pack 根目录内；不能依赖调用方先做路径过滤。
    """
    components = (case_id, profile_id, run_name)
    invalid_component = any(
        (not _RUN_COMPONENT_RE.fullmatch(item or "") and not (index == 1 and item == "_"))
        or item in {".", ".."}
        for index, item in enumerate(components)
    )
    if invalid_component:
        raise ValueError("invalid sealed run component")
    pack_resolved = pack_root.resolve()
    candidates = (
        pack_root / "runs" / case_id / profile_id / run_name,
        pack_root / "runs" / case_id / run_name,
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(pack_resolved)
        except ValueError:
            continue
        if resolved.is_dir():
            return resolved
    # 返回安全的首选路径，让上层产生一致的 not-found 错误。
    return candidates[0]


def sealed_index_integrity_ok(pack_root: Path) -> bool:
    """轻量校验 summary 是否仍与 artifact hash manifest 一致。"""
    try:
        manifest = _read_json(pack_root / "artifact-hashes.json")
        expected = manifest.get("artifacts", {}).get("summary.json")
        return bool(expected) and expected == sha256_file(pack_root / "summary.json")
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def validate_sealed_run(pack_root: Path, run_dir: Path) -> None:
    """验证本次回放会读取的文件都受 pack 的 SHA-256 manifest 约束。"""
    if not sealed_index_integrity_ok(pack_root):
        raise ValueError("sealed pack summary integrity failed")
    manifest = _read_json(pack_root / "artifact-hashes.json")
    expected_artifacts = manifest.get("artifacts", {})
    required = [
        run_dir / "agent-transcript.jsonl",
        run_dir / "world-before-intent.json",
        run_dir / "verdict.json",
    ]
    if (run_dir / "tool-intent.json").is_file():
        required.extend(
            [
                run_dir / "tool-intent.json",
                run_dir / "null" / "branch-verdict.json",
                run_dir / "null" / "ledger.jsonl",
                run_dir / "null" / "world-out.json",
                run_dir / "xaguard" / "branch-verdict.json",
                run_dir / "xaguard" / "ledger.jsonl",
                run_dir / "xaguard" / "world-out.json",
            ]
        )
        audit = run_dir / "xaguard" / "xa-guard-audit" / "audit.jsonl"
        if audit.is_file():
            required.append(audit)
    for path in required:
        if not path.is_file():
            raise ValueError(f"sealed replay artifact missing: {path.name}")
        relative = path.resolve().relative_to(pack_root.resolve()).as_posix()
        expected = expected_artifacts.get(relative)
        if not expected or expected != sha256_file(path):
            raise ValueError(f"sealed replay artifact integrity failed: {path.name}")


def derive_replay_events(
    pack_root: Path,
    case_id: str,
    profile_id: str,
    run_name: str,
    emit: Callable[[dict[str, Any]], None],
    builder: EventBuilder,
) -> None:
    """读取一个封存 run 的 artifact，推导并发出完整事件流。"""
    run_dir = resolve_run_dir(pack_root, case_id, profile_id, run_name)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"sealed run not found: {case_id}/{profile_id}/{run_name}")
    validate_sealed_run(pack_root, run_dir)

    transcript_path = run_dir / "agent-transcript.jsonl"
    emit(
        builder.emit(
            "MODEL_RESPONDED",
            "MODEL_RESPONDED",
            branch="NONE",
            message="SEALED REPLAY：agent transcript 来自封存证据包",
            artifact_refs=[artifact_ref("agent-transcript.jsonl", "/", transcript_path)]
            if transcript_path.is_file()
            else None,
        )
    )

    intent_path = run_dir / "tool-intent.json"
    world_before_path = run_dir / "world-before-intent.json"
    if not intent_path.is_file():
        emit(
            builder.emit(
                "MODEL_SELF_DEFENSE",
                "MODEL_SELF_DEFENSE",
                message="封存 run 无 ToolIntent（模型未产生违规意图）；不是 Guard win",
                artifact_refs=[artifact_ref("verdict.json", "/model_attempt_violation", run_dir / "verdict.json")],
            )
        )
        emit(builder.emit("RUN_COMPLETED", "COMPLETE", message="SEALED REPLAY 结束"))
        return

    intent = _read_json(intent_path)
    emit(
        builder.emit(
            "INTENT_FROZEN",
            "INTENT_FROZEN",
            message="冻结 ToolIntent（hash 直接来自 tool-intent.json）",
            artifact_refs=[
                artifact_ref("tool-intent.json", "/arguments_sha256", intent_path),
                artifact_ref("world-before-intent.json", "/", world_before_path),
            ],
            intent={
                "tool_name": str(intent.get("tool_name", "unknown")),
                "arguments_sha256": str(intent.get("arguments_sha256", "")),
                "world_before_sha256": sha256_file(world_before_path),
                "intent_id": str(intent.get("intent_id", "")),
                "property_id": str(intent.get("property_id", "")),
                "target_summary": str(intent.get("target", ""))[:160],
            },
        )
    )

    # Null 分支
    emit(builder.emit("NULL_STARTED", "NULL_RUNNING", branch="NULL"))
    null_dir = run_dir / "null"
    null_verdict = _read_json(null_dir / "branch-verdict.json")
    emit(
        builder.emit(
            "NULL_COMPLETED",
            "NULL_COMPLETE",
            branch="NULL",
            message="Null 对照分支：同一 intent 直接执行",
            artifact_refs=[
                artifact_ref("ledger.jsonl", "/", null_dir / "ledger.jsonl"),
                artifact_ref("world-out.json", "/", null_dir / "world-out.json"),
            ],
            branch_result={
                "decision": str(null_verdict.get("decision", "unknown")),
                "intent_arguments_sha256": str(intent.get("arguments_sha256", "")),
                "downstream_call_count": _side_effect_delta(
                    world_before_path, null_dir / "world-out.json"
                ),
                "harm_observed": bool(null_verdict.get("harm_observed", False)),
                "world_before_sha256": sha256_file(world_before_path),
                "world_after_sha256": sha256_file(null_dir / "world-out.json"),
                "ledger_sha256": sha256_file(null_dir / "ledger.jsonl"),
            },
        )
    )

    # XA-Guard 分支
    emit(builder.emit("GUARD_STARTED", "GUARD_RUNNING", branch="GUARD"))
    guard_dir = run_dir / "xaguard"
    guard_verdict = _read_json(guard_dir / "branch-verdict.json")
    audit_path = guard_dir / "xa-guard-audit" / "audit.jsonl"
    audit_rows = _read_jsonl(audit_path)
    for gate_event in gate_rail_from_audit(audit_rows, guard_verdict):
        emit(
            builder.emit(
                "GUARD_GATE_RESULT",
                "GUARD_RUNNING",
                branch="GUARD",
                gate=gate_event,
                artifact_refs=[artifact_ref("audit.jsonl", "/", audit_path)]
                if audit_path.is_file()
                else None,
            )
        )
    emit(
        builder.emit(
            "GUARD_COMPLETED",
            "GUARD_COMPLETE",
            branch="GUARD",
            message=f"XA-Guard 分支：decision={guard_verdict.get('decision', 'unknown')}",
            artifact_refs=[
                artifact_ref("world-out.json", "/", guard_dir / "world-out.json"),
                artifact_ref("ledger.jsonl", "/", guard_dir / "ledger.jsonl"),
            ],
            branch_result={
                "decision": str(guard_verdict.get("decision", "unknown")),
                "intent_arguments_sha256": str(intent.get("arguments_sha256", "")),
                "downstream_call_count": _side_effect_delta(
                    world_before_path, guard_dir / "world-out.json"
                ),
                "harm_observed": bool(guard_verdict.get("harm_observed", False)),
                "world_before_sha256": sha256_file(world_before_path),
                "world_after_sha256": sha256_file(guard_dir / "world-out.json"),
                "ledger_sha256": sha256_file(guard_dir / "ledger.jsonl"),
            },
        )
    )

    verdict_path = run_dir / "verdict.json"
    emit(
        builder.emit(
            "RUN_COMPLETED",
            "COMPLETE",
            message="SEALED REPLAY 结束；结论以 verdict.json / summary.json 为准",
            artifact_refs=[
                artifact_ref("verdict.json", "/", verdict_path),
                artifact_ref("summary.json", "/", pack_root / "summary.json"),
                artifact_ref("artifact-hashes.json", "/", pack_root / "artifact-hashes.json"),
            ],
        )
    )


def list_sealed_runs(pack_root: Path) -> list[dict[str, str]]:
    """从封存包 summary.json 枚举可回放的 run。"""
    summary_path = pack_root / "summary.json"
    if not summary_path.is_file():
        return []
    summary = _read_json(summary_path)
    runs = []
    for item in summary.get("runs", []):
        run_name = f"run-{int(item['repeat_index']):03d}"
        profile = str(item.get("prompt_profile", "") or "")
        if (
            (profile and not _RUN_COMPONENT_RE.fullmatch(profile))
            or any(
                not _RUN_COMPONENT_RE.fullmatch(component or "")
                for component in (str(item["case_id"]), run_name)
            )
        ):
            continue
        decision = str(item.get("guard_decision", "") or item.get("xaguard_decision", ""))
        attempt = bool(
            item.get("model_attempt_violation", item.get("model_native_intent", False))
        )
        runs.append(
            {
                "case_id": str(item["case_id"]),
                "prompt_profile": profile or "_",
                "run_name": run_name,
                "guard_decision": decision,
                "attempt": attempt,
            }
        )
    return runs
