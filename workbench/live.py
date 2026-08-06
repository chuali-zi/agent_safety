"""LIVE RUN：接线真实 open-agent-range live_agent runner 与 XA-Guard live SUT。

只在调用方（支持环境）具备模型 Key 与 stdio 管道权限时才能真跑；任何失败
（无 key、无 manifest、WinError 5 等）都如实以 PREFLIGHT_FAILED / RUN_FAILED 呈现，
绝不伪造成功。事件 hash 全部来自 runner 实际写出的 artifact。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
OAR_ROOT = REPO_ROOT / "open-agent-range"
if str(OAR_ROOT) not in sys.path:
    sys.path.insert(0, str(OAR_ROOT))

from .events import EventBuilder, artifact_ref, sha256_file  # noqa: E402
from .replay import gate_rail_from_audit, _read_json, _read_jsonl, _side_effect_delta  # noqa: E402


def preflight(manifest_path: Path, env_file: Path | None, xa_guard_root: Path) -> list[dict[str, Any]]:
    """LIVE 前置检查；只返回布尔与脱敏 detail，不回显任何 secret。"""
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail[:300]})

    try:
        from kernel.live_agent.models import ExperimentConfig

        config = ExperimentConfig.load(manifest_path)
        add("manifest_loads", True, f"experiment_id={config.experiment_id}")
    except Exception as exc:  # noqa: BLE001 - preflight 必须如实报告任何失败
        add("manifest_loads", False, f"{type(exc).__name__}")
        return checks

    if env_file is not None and env_file.is_file():
        from kernel.live_agent.runner import load_local_env

        load_local_env(env_file)
        add("env_file_loaded", True, env_file.name)
    else:
        add("env_file_loaded", env_file is None, "no env file provided")

    add("provider_key_present", bool(os.environ.get("DEEPSEEK_API_KEY", "")), "presence only")
    add("world_path_exists", Path(config.world_path).is_file(), "scenario world file")
    add("xa_guard_root_exists", (xa_guard_root / "src" / "xa_guard").is_dir(), "live SUT root")
    try:
        work_probe = REPO_ROOT / ".runtime" / "workbench"
        work_probe.mkdir(parents=True, exist_ok=True)
        probe = work_probe / ".probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        add("work_root_writable", True, "")
    except OSError as exc:
        add("work_root_writable", False, type(exc).__name__)
    return checks


def run_live(
    *,
    manifest_path: Path,
    env_file: Path | None,
    case_id: str,
    evidence_dir: Path,
    xa_guard_root: Path,
    emit: Callable[[dict], None],
    builder: EventBuilder,
) -> None:
    """后台线程入口：真实模型 → 冻结 intent → Null/Guard 分叉 → 逐 Gate 事件。"""
    from kernel.live_agent.models import ExperimentConfig
    from kernel.live_agent.provider import DeepSeekAdapter
    from kernel.live_agent.runner import (
        LiveAgentRunner,
        load_local_env,
    )

    emit(builder.emit("PREFLIGHT_STARTED", "PREFLIGHTING", message="LIVE：检查 manifest/provider/runtime"))
    checks = preflight(manifest_path, env_file, xa_guard_root)
    failed = [c["name"] for c in checks if not c["ok"]]
    if failed:
        emit(
            builder.emit(
                "PREFLIGHT_FAILED",
                "PREFLIGHT_FAILED",
                message=f"LIVE preflight 失败：{', '.join(failed)}（如实失败，未伪造）",
            )
        )
        emit(builder.emit("RUN_FAILED", "FAILED", message="preflight failed"))
        return
    emit(builder.emit("PREFLIGHT_READY", "PREFLIGHT_READY", message="LIVE preflight 通过"))

    if env_file is not None and env_file.is_file():
        load_local_env(env_file)
    config = ExperimentConfig.load(manifest_path)
    selected = [case for case in config.cases_for_phase("holdout") if case.case_id == case_id]
    if not selected:
        emit(
            builder.emit(
                "RUN_FAILED",
                "FAILED",
                message=f"manifest 中不存在 holdout case：{case_id}",
            )
        )
        return
    case = selected[0]
    profile = config.prompt_profiles[0]

    adapter = DeepSeekAdapter(
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        base_url=config.base_url,
        model=config.model,
        thinking=config.thinking,
        temperature=config.temperature,
        timeout_seconds=config.timeout_seconds,
        http_retries=config.http_retries,
    )

    original_next_turn = adapter.next_turn

    def emitting_next_turn(messages, tools):
        emit(
            builder.emit(
                "MODEL_REQUESTED",
                "MODEL_REQUESTED",
                message=f"LIVE：请求真实模型 {config.model}（tool_choice=auto）",
            )
        )
        turn = original_next_turn(messages, tools)
        emit(
            builder.emit(
                "MODEL_RESPONDED",
                "MODEL_RESPONDED",
                message=f"LIVE：模型返回，tool_calls={len(getattr(turn, 'tool_calls', []) or [])}",
            )
        )
        return turn

    adapter.next_turn = emitting_next_turn  # 只包本实例，不改 kernel 代码

    runner = LiveAgentRunner(
        config,
        adapter,
        evidence_dir=evidence_dir,
        guard_mode="live",
        xa_guard_root=xa_guard_root,
    )

    original_fork = runner._execute_fork

    def emitting_fork(case_, scenario, intent, world, ledger, run_dir, *, messages):
        intent_path = run_dir / "tool-intent.json"
        world_before_path = run_dir / "world-before-intent.json"
        emit(
            builder.emit(
                "INTENT_FROZEN",
                "INTENT_FROZEN",
                message="LIVE：冻结 ToolIntent，Null/Guard 两臂复用同一 hash",
                artifact_refs=[
                    artifact_ref("tool-intent.json", "/arguments_sha256", intent_path),
                    artifact_ref("world-before-intent.json", "/", world_before_path),
                ],
                intent={
                    "tool_name": intent.tool_name,
                    "arguments_sha256": intent.arguments_sha256,
                    "world_before_sha256": sha256_file(world_before_path),
                    "intent_id": intent.intent_id,
                    "property_id": case_.property_id,
                    "target_summary": str(intent.target)[:160],
                },
            )
        )
        emit(
            builder.emit(
                "NULL_STARTED",
                "NULL_RUNNING",
                branch="NULL",
                message="LIVE：runner 开始执行冻结 intent 的 Null/Guard 因果分叉",
            )
        )
        return original_fork(
            case_, scenario, intent, world, ledger, run_dir, messages=messages
        )

    runner._execute_fork = emitting_fork  # 包实例方法，不改 kernel 代码

    run_dir = evidence_dir / "runs" / case.case_id / profile.profile_id / "run-001"
    try:
        result = runner.run_once(case, profile, repeat_index=1, run_dir=run_dir)
    except Exception as exc:  # noqa: BLE001 - live 边界，如实报告
        emit(
            builder.emit(
                "RUN_FAILED",
                "FAILED",
                message=f"LIVE 运行失败：{type(exc).__name__}（本环境可能无管道/网络权限）",
            )
        )
        return

    transcript_path = run_dir / "agent-transcript.jsonl"
    if transcript_path.is_file():
        emit(
            builder.emit(
                "MODEL_RESPONDED",
                "MODEL_RESPONDED",
                message="LIVE：agent transcript 已落盘",
                artifact_refs=[artifact_ref("agent-transcript.jsonl", "/", transcript_path)],
            )
        )

    if result.get("infra_status") != "ok":
        emit(
            builder.emit(
                "RUN_FAILED",
                "FAILED",
                message=f"LIVE infra 失败：{result.get('infra_status')}（如实展示，不重试伪装）",
                artifact_refs=[artifact_ref("verdict.json", "/infra_status", run_dir / "verdict.json")],
            )
        )
        return

    if not result.get("model_attempt_violation"):
        emit(
            builder.emit(
                "MODEL_SELF_DEFENSE",
                "MODEL_SELF_DEFENSE",
                message="模型未产生违规 ToolIntent（MODEL_SELF_DEFENSE，不是 Guard win）",
                artifact_refs=[artifact_ref("verdict.json", "/model_attempt_violation", run_dir / "verdict.json")],
            )
        )
        emit(builder.emit("RUN_COMPLETED", "COMPLETE", message="LIVE 结束：无 intent"))
        return

    world_before_path = run_dir / "world-before-intent.json"
    null_dir = run_dir / "null"
    null_verdict = _read_json(null_dir / "branch-verdict.json")
    emit(
        builder.emit(
            "NULL_COMPLETED",
            "NULL_COMPLETE",
            branch="NULL",
            message="LIVE：Null 对照分支完成",
            artifact_refs=[
                artifact_ref("ledger.jsonl", "/", null_dir / "ledger.jsonl"),
                artifact_ref("world-out.json", "/", null_dir / "world-out.json"),
            ],
            branch_result={
                "decision": str(null_verdict.get("decision", "unknown")),
                "intent_arguments_sha256": str(result.get("intent_arguments_sha256", "")),
                "downstream_call_count": _side_effect_delta(world_before_path, null_dir / "world-out.json"),
                "harm_observed": bool(null_verdict.get("harm_observed", False)),
                "world_before_sha256": sha256_file(world_before_path),
                "world_after_sha256": sha256_file(null_dir / "world-out.json"),
                "ledger_sha256": sha256_file(null_dir / "ledger.jsonl"),
            },
        )
    )

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
            message=f"LIVE：XA-Guard 分支 decision={guard_verdict.get('decision', 'unknown')}",
            artifact_refs=[
                artifact_ref("world-out.json", "/", guard_dir / "world-out.json"),
                artifact_ref("ledger.jsonl", "/", guard_dir / "ledger.jsonl"),
            ],
            branch_result={
                "decision": str(guard_verdict.get("decision", "unknown")),
                "intent_arguments_sha256": str(result.get("intent_arguments_sha256", "")),
                "downstream_call_count": _side_effect_delta(world_before_path, guard_dir / "world-out.json"),
                "harm_observed": bool(guard_verdict.get("harm_observed", False)),
                "world_before_sha256": sha256_file(world_before_path),
                "world_after_sha256": sha256_file(guard_dir / "world-out.json"),
                "ledger_sha256": sha256_file(guard_dir / "ledger.jsonl"),
            },
        )
    )
    emit(
        builder.emit(
            "RUN_COMPLETED",
            "COMPLETE",
            message="LIVE 结束；结论以 verdict.json 与 audit.jsonl 为准",
            artifact_refs=[
                artifact_ref("verdict.json", "/", run_dir / "verdict.json"),
                artifact_ref("audit.jsonl", "/", audit_path),
            ],
        )
    )
