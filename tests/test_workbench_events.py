"""Workbench 事件 schema 校验测试：所有模式产出的事件必须符合 handoff schema。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workbench.events import EventBuilder, validate_event  # noqa: E402
from workbench.synthetic import OperatorChannel, run_synthetic  # noqa: E402


def _collect_synthetic(scenario: str) -> list[dict]:
    events: list[dict] = []
    builder = EventBuilder("run_test_synth01", "EXAMPLE_SYNTHETIC")

    def emit(event: dict) -> None:
        events.append(event)

    channel = OperatorChannel()
    if scenario == "hitl":
        # 预先设定操作序列：approve → replay，避免等待
        import threading

        def driver() -> None:
            import time

            time.sleep(0.5)
            channel.submit("approve")
            time.sleep(2.0)
            channel.submit("replay")

        threading.Thread(target=driver, daemon=True).start()
    run_synthetic(scenario, emit, builder, operator_channel=channel, step_delay=0.01)
    return events


@pytest.mark.parametrize("scenario", ["d2", "utility", "hitl", "verifier"])
def test_synthetic_events_are_schema_valid(scenario: str) -> None:
    events = _collect_synthetic(scenario)
    assert len(events) >= 4
    for event in events:
        validate_event(event)
        assert event["run_mode"] == "EXAMPLE_SYNTHETIC"


def test_synthetic_d2_shows_guard_deny_and_null_harm() -> None:
    events = _collect_synthetic("d2")
    null_completed = next(e for e in events if e["event_type"] == "NULL_COMPLETED")
    assert null_completed["branch_result"]["harm_observed"] is True
    gate_events = [e for e in events if e["event_type"] == "GUARD_GATE_RESULT"]
    statuses = {e["gate"]["gate_id"]: e["gate"]["status"] for e in gate_events}
    assert statuses["GATE4"] == "DENY"
    assert statuses["GATE5"] == "NOT_REACHED"
    guard_completed = next(e for e in events if e["event_type"] == "GUARD_COMPLETED")
    assert guard_completed["branch_result"]["downstream_call_count"] == 0
    assert (
        null_completed["branch_result"]["intent_arguments_sha256"]
        == guard_completed["branch_result"]["intent_arguments_sha256"]
    )


def test_synthetic_hitl_pending_then_single_execution() -> None:
    events = _collect_synthetic("hitl")
    types = [e["event_type"] for e in events]
    assert "GUARD_PENDING_APPROVAL" in types
    assert "OPERATOR_APPROVED" in types
    guard_completed = next(e for e in events if e["event_type"] == "GUARD_COMPLETED")
    assert guard_completed["branch_result"]["downstream_call_count"] == 1
    # replay 拒绝事件存在且 downstream 仍为 1
    assert "OPERATOR_REJECTED" in types


def test_invalid_event_rejected_by_validator() -> None:
    builder = EventBuilder("run_test_bad0001", "EXAMPLE_SYNTHETIC")
    import jsonschema

    with pytest.raises(jsonschema.ValidationError):
        builder.emit("NOT_A_TYPE", "COMPLETE")


def test_hitl_replay_cannot_be_misread_as_initial_approval() -> None:
    events: list[dict] = []
    channel = OperatorChannel()
    assert channel.submit("replay") is True
    run_synthetic(
        "hitl",
        events.append,
        EventBuilder("run_test_replay01", "EXAMPLE_SYNTHETIC"),
        operator_channel=channel,
        step_delay=0,
    )
    types = [event["event_type"] for event in events]
    assert "OPERATOR_APPROVED" not in types
    assert types[-1] == "RUN_FAILED"
