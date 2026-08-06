"""SEALED REPLAY 推导测试：从真实封存包推导事件，hash 与 Gate 映射必须来自 artifact。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workbench.events import EventBuilder, validate_event  # noqa: E402
from workbench.replay import (  # noqa: E402
    deciding_gate_from_reason,
    derive_replay_events,
    gate_rail_from_audit,
    list_sealed_runs,
)

PACKS_ROOT = REPO_ROOT / "open-agent-range" / ".runtime" / "live-agent"
V2_PACK = PACKS_ROOT / "holdout-v2-formal-20260803"
UTILITY_PACK = PACKS_ROOT / "public-utility-formal-20260804"


def _derive(pack: Path, case: str, profile: str, run_name: str) -> list[dict]:
    events: list[dict] = []
    builder = EventBuilder("run_test_sealed01", "SEALED_REPLAY")
    derive_replay_events(pack, case, profile, run_name, events.append, builder)
    return events


@pytest.mark.skipif(not V2_PACK.is_dir(), reason="sealed v2 pack not present")
def test_v2_deny_run_derivation() -> None:
    events = _derive(V2_PACK, "D2-HOLDOUT-LOG-BYPASS", "neutral-tool", "run-001")
    for event in events:
        validate_event(event)
        assert event["run_mode"] == "SEALED_REPLAY"

    run_dir = V2_PACK / "runs" / "D2-HOLDOUT-LOG-BYPASS" / "neutral-tool" / "run-001"
    intent_doc = json.loads((run_dir / "tool-intent.json").read_text(encoding="utf-8"))

    frozen = next(e for e in events if e["event_type"] == "INTENT_FROZEN")
    # hash 必须直接来自 artifact，不允许 UI/适配层自造
    assert frozen["intent"]["arguments_sha256"] == intent_doc["arguments_sha256"]

    gate_events = [e for e in events if e["event_type"] == "GUARD_GATE_RESULT"]
    assert len(gate_events) == 6
    statuses = {e["gate"]["gate_id"]: e["gate"]["status"] for e in gate_events}
    verdict = json.loads((run_dir / "xaguard" / "branch-verdict.json").read_text(encoding="utf-8"))
    audit_reason = verdict["audit"][0]["reason"]
    deciding = deciding_gate_from_reason(audit_reason)
    assert deciding is not None
    assert statuses[f"GATE{deciding}"] == "DENY"
    assert statuses["GATE5"] == "NOT_REACHED"
    assert statuses["GATE6"] == "ALLOW"
    for earlier in range(1, deciding):
        assert statuses[f"GATE{earlier}"] == "UNKNOWN"

    null_completed = next(e for e in events if e["event_type"] == "NULL_COMPLETED")
    guard_completed = next(e for e in events if e["event_type"] == "GUARD_COMPLETED")
    assert null_completed["branch_result"]["harm_observed"] is True
    assert guard_completed["branch_result"]["harm_observed"] is False
    assert guard_completed["branch_result"]["downstream_call_count"] == 0
    # 因果不变量：两臂 world-before 一致
    assert (
        null_completed["branch_result"]["world_before_sha256"]
        == guard_completed["branch_result"]["world_before_sha256"]
    )


@pytest.mark.skipif(not UTILITY_PACK.is_dir(), reason="sealed utility pack not present")
def test_utility_allow_run_derivation() -> None:
    runs = list_sealed_runs(UTILITY_PACK)
    assert runs, "utility pack has no runs"
    allow_runs = [r for r in runs if r["guard_decision"] == "allow" and r["attempt"]]
    assert allow_runs, "no allow run found in utility pack"
    target = allow_runs[0]
    events = _derive(UTILITY_PACK, target["case_id"], target["prompt_profile"], target["run_name"])
    for event in events:
        validate_event(event)
    guard_completed = next(e for e in events if e["event_type"] == "GUARD_COMPLETED")
    assert guard_completed["branch_result"]["decision"] == "allow"
    assert guard_completed["branch_result"]["downstream_call_count"] == 1
    # allow 分支：audit 无逐 Gate 记录，GATE1-4 不得渲染为"安全通过"
    gate_events = [e for e in events if e["event_type"] == "GUARD_GATE_RESULT"]
    statuses = {e["gate"]["gate_id"]: e["gate"]["status"] for e in gate_events}
    assert statuses["GATE6"] == "ALLOW"
    assert statuses["GATE1"] == "UNKNOWN"


def test_gate_rail_without_audit_is_honest() -> None:
    gates = gate_rail_from_audit([], {})
    statuses = {g["gate_id"]: g["status"] for g in gates}
    assert statuses["GATE5"] == "NOT_REACHED"
    for gate_id in ("GATE1", "GATE2", "GATE3", "GATE4", "GATE6"):
        assert statuses[gate_id] == "UNKNOWN"


def test_deciding_gate_from_reason() -> None:
    assert deciding_gate_from_reason("gate4_taint: CONFIDENTIAL 外发拦截") == 4
    assert deciding_gate_from_reason("gate3_policy: 重要操作授权") == 3
    assert deciding_gate_from_reason("allow") is None
