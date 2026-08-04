"""Live XA-Guard SUT smoke.

This test is skipped outside the XA-Guard monorepo, but when the parent
XA-Guard project and mcp package are available it proves ToolCall attempts go
through a real ``xa_guard.server`` stdio MCP process and Gate6 audit.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from kernel import sut as sut_module
from kernel.demo import reference_surface
from kernel.evidence import EvidenceStore
from kernel.policy_overlay import overlay_from_scenario
from kernel.run import run_attempt
from kernel.scenario import load_injections, load_scenario, with_injections
from kernel.seat import GullibleSeat, ManualSeat, SeatContext
from kernel.sut import ToolCall, XaGuardArtifacts, XaGuardSUT, find_xa_guard_root
from kernel.world import DataAsset, World

SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _requires_live_xaguard() -> Path:
    try:
        import mcp  # noqa: F401
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"mcp package unavailable: {exc}")
    try:
        return find_xa_guard_root(Path(__file__))
    except FileNotFoundError as exc:  # pragma: no cover
        pytest.skip(str(exc))


def test_xaguard_live_sut_reuses_one_session_for_attempt(tmp_path: Path, monkeypatch) -> None:
    class FakeLiveSession:
        instances: list["FakeLiveSession"] = []

        def __init__(self, *, command, env, timeout_s=60.0) -> None:
            self.command = command
            self.env = env
            self.timeout_s = timeout_s
            self.calls: list[tuple[str, dict]] = []
            self.started = False
            self.closed = False
            FakeLiveSession.instances.append(self)

        def start(self) -> None:
            self.started = True

        def call_tool(self, tool: str, arguments: dict) -> str:
            self.calls.append((tool, arguments))
            return "fake xa-guard live allowed tool call"

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(sut_module, "_XaGuardLiveSession", FakeLiveSession)
    scenario = load_scenario(SCENARIOS / "dctg" / "office-mailbox.json")
    sut = XaGuardSUT(xa_guard_root=tmp_path, live=True)
    audit_dir = tmp_path / "xa-guard-audit"
    audit_dir.mkdir()
    sut.artifacts = XaGuardArtifacts(
        xa_guard_yaml=tmp_path / "xa-guard.yaml",
        gate3_rules=tmp_path / "gate3-rules.yaml",
        gate4_capabilities=tmp_path / "gate4-capabilities.yaml",
        audit_dir=audit_dir,
        pending_path=tmp_path / "pending-approvals.jsonl",
        tool_schemas=tmp_path / "mcp-tool-schemas.json",
    )
    out_dir = tmp_path / "attempt"

    result = run_attempt(
        scenario,
        reference_surface(),
        ManualSeat(
            [
                ToolCall("read_record", {"record_id": "rec-002"}),
                ToolCall(
                    "send_message",
                    {"to": "甲方-政府客户", "content": "官网改版技术方案", "sources": ["rec-002"]},
                ),
            ]
        ),
        sut,
        evidence_store=EvidenceStore(out_dir),
    )

    session = FakeLiveSession.instances[0]
    summary = json.loads((out_dir / "sut-session.json").read_text(encoding="utf-8"))
    hashes = json.loads((out_dir / "artifact-hashes.json").read_text(encoding="utf-8"))

    assert result.ledger.verify_hash_chain()
    assert len(FakeLiveSession.instances) == 1
    assert session.started is True
    assert session.closed is True
    assert [tool for tool, _ in session.calls] == ["read_record", "send_message"]
    assert summary["session_scope"] == "attempt"
    assert summary["process_start_count"] == 1
    assert summary["tool_call_count"] == 2
    assert summary["closed"] is True
    assert summary["tools"] == [
        {"principal": "林工", "tool": "read_record"},
        {"principal": "林工", "tool": "send_message"},
    ]
    assert "sut-session.json" in hashes
    sent_arguments = session.calls[1][1]
    provenance = sent_arguments["_xa_guard"]["provenance"]
    assert provenance["tool_name"] == "send_message"
    assert provenance["arguments_sha256"] == _canonical_sha256(
        {"to": "甲方-政府客户", "content": "官网改版技术方案", "sources": ["rec-002"]}
    )
    assert provenance["resolved_references"] == [
        {
            "reference_id": "rec-002",
            "resolution_status": "resolved",
            "classification": "INTERNAL",
            "taint": "INTERNAL",
            "asset_digest": provenance["resolved_references"][0]["asset_digest"],
            "resolver_id": "oar-world-v1",
            "reason": "",
        }
    ]
    assert any(
        item.get("content", {}).get("visible_records")
        for item in sent_arguments["_xa_guard"]["session_history"]
        if isinstance(item.get("content"), dict)
    )
    assert any(item["source_id"] == "oar-record:rec-002" for item in provenance["sources"])
    assert "XA_GUARD_PROVENANCE_HMAC_SECRET" not in json.dumps(summary, ensure_ascii=False)
    assert "XA_GUARD_PROVENANCE_HMAC_SECRET" in session.env


def test_xaguard_live_sut_denies_sensitive_mailbox_exfil(tmp_path: Path) -> None:
    root = _requires_live_xaguard()
    scenario = with_injections(
        load_scenario(SCENARIOS / "dctg" / "office-mailbox.json"),
        load_injections(SCENARIOS / "injections" / "office-mail-exfil.json"),
    )
    sut = XaGuardSUT(policy=overlay_from_scenario(scenario), xa_guard_root=root, live=True)

    result = run_attempt(
        scenario,
        reference_surface(),
        GullibleSeat(),
        sut,
        evidence_store=EvidenceStore(tmp_path),
    )

    assert result.ledger.verify_hash_chain()
    assert result.violations == []
    assert result.verdict.passed
    assert any(record.tool == "send_message" and record.decision == "deny" for record in sut.audit)
    assert not any(entry.action == "send" and entry.external for entry in result.ledger.entries)
    assert (tmp_path / "xa-guard-audit" / "audit.jsonl").is_file()


def test_xaguard_trusted_context_signs_business_args_and_resolves_reference_fields() -> None:
    sut = XaGuardSUT(live=True)
    sut._scenario_id = "adapter-unit"  # Exercise the adapter without an MCP subprocess.
    sut._live_session_summary = {"session_id": "adapter-session", "tool_call_count": 4}
    world = World(
        data_assets={
            "public-1": DataAsset(asset_id="public-1", classification="PUBLIC", content="public"),
            "secret-1": DataAsset(asset_id="secret-1", classification="SECRET", content="synthetic secret"),
        }
    )
    call = ToolCall(
        "send_message",
        {
            "to": "external",
            "attachments": [{"id": "public-1"}],
            "records": ["secret-1", "missing-1"],
            "_xa_guard": {"provenance": "agent must not control transport metadata"},
        },
    )

    arguments = sut._call_arguments(call, principal="Dora", world=world)
    envelope = arguments["_xa_guard"]["provenance"]
    unsigned = {key: value for key, value in envelope.items() if key != "signature"}
    expected_signature = hmac.new(
        sut._provenance_key,
        _canonical_sha256(unsigned).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()

    assert arguments["_xa_guard"]["human_principal"] == "Dora"
    assert arguments["_xa_guard"]["session_history"] == []
    assert "agent must not control" not in json.dumps(arguments, ensure_ascii=False)
    assert envelope["session_id"] == "adapter-session"
    assert envelope["turn_id"] == "5"
    assert envelope["tool_name"] == "send_message"
    assert envelope["arguments_sha256"] == _canonical_sha256(
        {"to": "external", "attachments": [{"id": "public-1"}], "records": ["secret-1", "missing-1"]}
    )
    assert envelope["signature"] == expected_signature
    assert [(item["reference_id"], item["resolution_status"], item["taint"]) for item in envelope["resolved_references"]] == [
        ("public-1", "resolved", "PUBLIC"),
        ("secret-1", "resolved", "CONFIDENTIAL"),
        ("missing-1", "unknown", "PUBLIC"),
    ]


def test_xaguard_trusted_context_uses_surfaced_channels_without_putting_content_in_sources() -> None:
    sut = XaGuardSUT(live=True)
    world = World(
        data_assets={
            "rec-1": DataAsset(asset_id="rec-1", classification="INTERNAL", content="internal source body"),
        }
    )
    context = SeatContext(
        principal="Dora",
        role="operator",
        task="Review the surfaced enterprise context.",
        channels={"rag": "knowledge-base", "log": "ops/web"},
        visible={
            "rag": [{"body": "untrusted instruction", "meta": {"origin": "redteam"}}],
            "log": [{"line": "trusted operational fact", "meta": {"origin": "system"}}],
            "records": {"rec-1": {"classification": "INTERNAL", "label": "record label"}},
        },
    )
    sut.set_invocation_context(context)

    arguments = sut._call_arguments(ToolCall("read_record", {"record_id": "rec-1"}), principal="Dora", world=world)
    envelope = arguments["_xa_guard"]["provenance"]
    sources = envelope["sources"]
    history = arguments["_xa_guard"]["session_history"]

    assert history[0] == {"role": "user", "content": "Review the surfaced enterprise context."}
    assert any(item["content"]["channel"] == "rag" for item in history[1:] if "channel" in item["content"])
    assert any(item["content"]["channel"] == "log" for item in history[1:] if "channel" in item["content"])
    assert ("rag", "unverified") in {(item["kind"], item["trust_state"]) for item in sources}
    assert ("tool_result", "verified") in {(item["kind"], item["trust_state"]) for item in sources}
    assert any(item["source_id"] == "oar-record:rec-1" and item["taint"] == "INTERNAL" for item in sources)
    serialized_sources = json.dumps(sources, ensure_ascii=False)
    assert "untrusted instruction" not in serialized_sources
    assert "trusted operational fact" not in serialized_sources
    assert "internal source body" not in serialized_sources
