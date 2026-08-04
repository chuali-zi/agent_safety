from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from xa_guard.config import GateConfig
from xa_guard.gates.base import GateStage
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.provenance import (
    ProvenanceSource,
    ResolutionStatus,
    ResolvedReference,
    TrustState,
    TrustedContextEnvelope,
    canonical_sha256,
)
from xa_guard.types import GateContext, InputSource, TaintLabel


def _envelope() -> TrustedContextEnvelope:
    now = datetime.now(timezone.utc)
    return TrustedContextEnvelope(
        schema_version="1.0",
        session_id="session-7",
        turn_id="turn-3",
        task_id="task-9",
        human_principal="alice",
        agent_id="office-agent",
        tenant_id="acme",
        history_digest=canonical_sha256([]),
        sources=(
            ProvenanceSource(
                source_id="rag-1",
                kind="rag",
                locator_digest="a" * 64,
                content_digest="b" * 64,
                trust_state=TrustState.VERIFIED,
                taint=TaintLabel.INTERNAL,
            ),
        ),
        resolved_references=(
            ResolvedReference(
                reference_id="record-17",
                status=ResolutionStatus.RESOLVED,
                classification=TaintLabel.CONFIDENTIAL,
                taint=TaintLabel.CONFIDENTIAL,
                asset_digest="c" * 64,
                resolver_id="catalog-v1",
                reason="this text must not be copied into the audit summary",
            ),
        ),
        policy_bundle_sha="d" * 64,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
        nonce="raw-nonce-must-not-be-audited",
        tool_name="send_message",
        arguments_sha256=canonical_sha256({"sources": ["record-17"]}),
        key_id="adapter-key-1",
        signature="signature-must-not-be-audited",
    )


def _record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8").strip())


def test_gate6_records_only_safe_verified_provenance_summary(tmp_path: Path) -> None:
    envelope = _envelope()
    ctx = GateContext(
        tool_name="send_message",
        arguments={"sources": ["record-17"]},
        session_history=[],
        input_sources=[InputSource.RAG],
        provenance=envelope,
        provenance_verified=True,
        tenant_id="acme",
    )
    gate = Gate6Audit(
        GateConfig(
            enabled=True,
            options={"audit_dir": str(tmp_path), "hash_algo": "sha256"},
        )
    )

    result = gate(ctx, GateStage.OUTBOUND)
    record = _record(Path(result.metadata["audit_path"]))

    assert record["gen_ai.provenance.verified"] is True
    assert record["gen_ai.provenance.session_id"] == "session-7"
    assert record["gen_ai.provenance.input_sources"] == ["rag"]
    assert record["gen_ai.provenance.sources"] == [
        {
            "source_id": "rag-1",
            "kind": "rag",
            "locator_digest": "a" * 64,
            "content_digest": "b" * 64,
            "trust_state": "verified",
            "taint": "INTERNAL",
        }
    ]
    assert record["gen_ai.provenance.resolved_references"][0] == {
        "reference_id": "record-17",
        "status": "resolved",
        "classification": "CONFIDENTIAL",
        "taint": "CONFIDENTIAL",
        "asset_digest": "c" * 64,
        "resolver_id": "catalog-v1",
    }
    serialized = json.dumps(record, ensure_ascii=False)
    assert envelope.signature not in serialized
    assert envelope.nonce not in serialized
    assert envelope.resolved_references[0].reason not in serialized


def test_gate6_marks_transport_without_envelope_as_unknown(tmp_path: Path) -> None:
    ctx = GateContext(
        tool_name="read_file",
        arguments={"path": "README.md"},
        input_sources=[InputSource.UNKNOWN],
    )
    gate = Gate6Audit(
        GateConfig(
            enabled=True,
            options={"audit_dir": str(tmp_path), "hash_algo": "sha256"},
        )
    )

    result = gate(ctx, GateStage.OUTBOUND)
    record = _record(Path(result.metadata["audit_path"]))

    assert record["gen_ai.provenance.verified"] is False
    assert record["gen_ai.provenance.input_sources"] == ["unknown"]
    assert record["gen_ai.provenance.sources"] == []
    assert record["gen_ai.provenance.digest"] == ""
