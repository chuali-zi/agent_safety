"""Workbench API 测试：artifact 白名单、路径穿越、未知字段、run 生命周期。"""

from __future__ import annotations

import http.client
import json
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workbench.server import WorkbenchConfig, make_handler  # noqa: E402

PACKS_ROOT = REPO_ROOT / "open-agent-range" / ".runtime" / "live-agent"
V2_PACK = PACKS_ROOT / "holdout-v2-formal-20260803"


@pytest.fixture()
def client(tmp_path):
    config = WorkbenchConfig(
        manifest=REPO_ROOT / "open-agent-range" / "scenarios" / "live-agent" / "p0-d1-d3-v2.json",
        env_file=None,
        packs_root=PACKS_ROOT,
        work_root=tmp_path,
        xa_guard_root=REPO_ROOT,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def request(method: str, path: str, body: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        payload = json.dumps(body).encode() if body is not None else None
        conn.request(
            method,
            path,
            body=payload,
            headers={"Content-Type": "application/json"} if body else {},
        )
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return resp.status, data

    yield request
    server.shutdown()


def _wait_events(request, run_id: str, want_type: str, timeout: float = 15.0) -> list[dict]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, data = request("GET", f"/api/live/events?run_id={run_id}")
        if any(e["event_type"] == want_type for e in data["events"]):
            return data["events"]
        time.sleep(0.2)
    raise AssertionError(f"event {want_type} not seen within {timeout}s")


def test_synthetic_run_end_to_end(client) -> None:
    status, accepted = client("POST", "/api/live/run", {
        "scenario_id": "synthetic:d2", "guard_mode": "live",
    })
    assert status == 200
    assert accepted["run_mode"] == "EXAMPLE_SYNTHETIC"
    assert accepted["run_id"].startswith("run_synth_")
    events = _wait_events(client, accepted["run_id"], "RUN_COMPLETED")
    assert all(e["run_mode"] == "EXAMPLE_SYNTHETIC" for e in events)


def test_run_rejects_unknown_fields(client) -> None:
    status, _ = client("POST", "/api/live/run", {
        "scenario_id": "synthetic:d2", "guard_mode": "live", "hack": True,
    })
    assert status == 400


def test_run_rejects_unknown_scenario(client) -> None:
    status, _ = client("POST", "/api/live/run", {
        "scenario_id": "synthetic:nope", "guard_mode": "live",
    })
    assert status == 400
    status, runs = client("GET", "/api/live/runs")
    assert status == 200
    assert runs["runs"] == []  # 无效请求不能留下幽灵 run


def test_events_unknown_run_id(client) -> None:
    status, _ = client("GET", "/api/live/events?run_id=run_nope_0000")
    assert status == 404


@pytest.mark.skipif(not V2_PACK.is_dir(), reason="sealed v2 pack not present")
def test_sealed_replay_and_artifact_security(client) -> None:
    scenario = "sealed:holdout-v2-formal-20260803/D2-HOLDOUT-LOG-BYPASS/neutral-tool/run-001"
    status, accepted = client("POST", "/api/live/run", {
        "scenario_id": scenario, "guard_mode": "live",
    })
    assert status == 200
    assert accepted["run_mode"] == "SEALED_REPLAY"
    _wait_events(client, accepted["run_id"], "RUN_COMPLETED")

    # artifact 白名单
    status, env = client(
        "GET", f"/api/live/artifact?run_id={accepted['run_id']}&name=tool-intent.json"
    )
    assert status == 200
    assert len(env["sha256"]) == 64
    # 同一 run 的 Null/Guard 有同名 world-out；不带事件 hash 时不得猜分支。
    status, _ = client(
        "GET", f"/api/live/artifact?run_id={accepted['run_id']}&name=world-out.json"
    )
    assert status == 409
    events_status, events_data = client(
        "GET", f"/api/live/events?run_id={accepted['run_id']}"
    )
    assert events_status == 200
    guard_done = next(
        event for event in events_data["events"] if event["event_type"] == "GUARD_COMPLETED"
    )
    guard_world = next(
        ref for ref in guard_done["artifact_refs"] if ref["name"] == "world-out.json"
    )
    status, exact = client(
        "GET",
        f"/api/live/artifact?run_id={accepted['run_id']}&name=world-out.json"
        f"&sha256={guard_world['sha256']}",
    )
    assert status == 200
    assert exact["sha256"] == guard_world["sha256"]
    assert exact["data"]["redacted"] is True

    # transcript 正文/工具参数只返回 digest 摘要，不进入 DOM。
    status, transcript = client(
        "GET", f"/api/live/artifact?run_id={accepted['run_id']}&name=agent-transcript.jsonl"
    )
    assert status == 200
    assert "<redacted sha256=" in json.dumps(transcript, ensure_ascii=False)
    # 白名单拒绝
    status, _ = client(
        "GET", f"/api/live/artifact?run_id={accepted['run_id']}&name=../../.env"
    )
    assert status == 400
    status, _ = client(
        "GET", f"/api/live/artifact?run_id={accepted['run_id']}&name=xa-guard.yaml"
    )
    assert status == 400
    # 绝对路径穿越
    status, _ = client(
        "GET", f"/api/live/artifact?run_id={accepted['run_id']}&name=C:%5CWindows%5Cwin.ini"
    )
    assert status == 400
    # artifact 响应不泄漏本机绝对路径
    status, env = client(
        "GET", f"/api/live/artifact?run_id={accepted['run_id']}&name=verdict.json"
    )
    assert status == 200
    assert "D:\\" not in json.dumps(env)


def test_pack_resolution_rejects_traversal(tmp_path) -> None:
    config = WorkbenchConfig(
        manifest=Path("missing.json"),
        env_file=None,
        packs_root=tmp_path,
        work_root=tmp_path / "work",
        xa_guard_root=REPO_ROOT,
    )
    assert config.resolve_pack("../escape") is None
    assert config.resolve_pack("a/b") is None
    assert config.resolve_pack("nonexistent") is None


def test_sealed_run_rejects_component_traversal(client) -> None:
    status, _ = client("POST", "/api/live/run", {
        "scenario_id": "sealed:holdout-v2-formal-20260803/../neutral-tool/run-001",
        "guard_mode": "live",
    })
    assert status == 400


def test_operator_channel_only_for_synthetic(client) -> None:
    status, accepted = client("POST", "/api/live/run", {
        "scenario_id": "synthetic:hitl", "guard_mode": "live",
    })
    assert status == 200
    _wait_events(client, accepted["run_id"], "GUARD_PENDING_APPROVAL")
    status, _ = client("POST", "/api/live/operator", {
        "run_id": accepted["run_id"], "action": "reject",
    })
    assert status == 200
    events = _wait_events(client, accepted["run_id"], "RUN_COMPLETED")
    assert any(e["event_type"] == "OPERATOR_REJECTED" for e in events)


def test_live_run_preflight_fails_honestly_without_key(client, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    status, resp = client("POST", "/api/live/preflight", {
        "scenario_id": "live:D2-HOLDOUT-LOG-BYPASS", "guard_mode": "live",
    })
    assert status == 200
    key_check = next(c for c in resp["checks"] if c["name"] == "provider_key_present")
    if not key_check["ok"]:
        assert resp["ok"] is False
        assert resp["safe_summary"]["provider_ready"] is False
