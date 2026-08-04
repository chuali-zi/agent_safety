"""Regression tests for trusted provenance contracts and pre-execution DLP."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from xa_guard.config import GateConfig
from xa_guard.gates.base import GateStage
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.policy.layered import set_global_source
from xa_guard.provenance import (
    MappingReferenceResolver,
    PROVENANCE_SCHEMA_VERSION,
    ResolutionStatus,
    ResolvedReference,
    TrustedContextEnvelope,
    canonical_sha256,
)
from xa_guard.types import Decision, GateContext, TaintLabel


def _gate(resolver: MappingReferenceResolver | None = None) -> Gate4Taint:
    return Gate4Taint(
        GateConfig(options={"tool_capabilities_file": "policies/baseline/gate4_capabilities.yaml"}),
        reference_resolver=resolver,
    )


def test_sensitive_sources_reference_denied_before_external_egress() -> None:
    gate = _gate(MappingReferenceResolver({
        "cit-1001": ResolvedReference(
            reference_id="cit-1001", status=ResolutionStatus.RESOLVED,
            classification=TaintLabel.CONFIDENTIAL, taint=TaintLabel.CONFIDENTIAL,
            asset_digest="a" * 64, resolver_id="oar-world",
        )
    }))

    result = gate.evaluate(GateContext(
        tool_name="send_email",
        arguments={"to": "outside@example.test", "body": "summary", "sources": ["cit-1001"]},
    ), GateStage.INBOUND)

    assert result.decision == Decision.DENY
    assert result.metadata["taint"] == "CONFIDENTIAL"
    assert result.metadata["resolved_references"] == [{
        "reference_id": "cit-1001", "status": "resolved", "classification": "CONFIDENTIAL",
        "taint": "CONFIDENTIAL", "asset_digest": "a" * 64, "resolver_id": "oar-world",
    }]


def test_public_sources_reference_allows_external_egress() -> None:
    gate = _gate(MappingReferenceResolver({
        "rec-002": ResolvedReference(
            reference_id="rec-002", status=ResolutionStatus.RESOLVED,
            classification=TaintLabel.PUBLIC, taint=TaintLabel.PUBLIC,
            asset_digest="b" * 64, resolver_id="oar-world",
        )
    }))

    result = gate.evaluate(GateContext(
        tool_name="send_email",
        arguments={"to": "outside@example.test", "body": "public proposal", "sources": ["rec-002"]},
    ), GateStage.INBOUND)

    assert result.decision == Decision.ALLOW
    assert result.metadata["taint"] == "PUBLIC"


def test_unknown_source_reference_fails_closed_for_external_egress() -> None:
    result = _gate().evaluate(GateContext(
        tool_name="send_email",
        arguments={"to": "outside@example.test", "body": "summary", "sources": ["not-in-catalog"]},
    ), GateStage.INBOUND)

    assert result.decision == Decision.DENY
    assert "trusted resolution" in result.risks[0]
    assert result.metadata["resolved_references"][0]["status"] == "unknown"


def test_agent_claimed_envelope_reference_is_ignored_until_adapter_marks_it_verified() -> None:
    arguments = {"to": "outside@example.test", "body": "public proposal", "sources": ["rec-002"]}
    envelope = TrustedContextEnvelope.from_dict({
        **_envelope_payload(arguments),
        "resolved_references": [{
            "reference_id": "rec-002", "resolution_status": "resolved", "classification": "PUBLIC",
            "taint": "PUBLIC", "asset_digest": "f" * 64, "resolver_id": "trusted-catalog",
        }],
    })
    gate = _gate()

    unverified = gate.evaluate(GateContext(tool_name="send_email", arguments=arguments, provenance=envelope), GateStage.INBOUND)
    verified = gate.evaluate(GateContext(
        tool_name="send_email", arguments=arguments, provenance=envelope, provenance_verified=True,
    ), GateStage.INBOUND)

    assert unverified.decision == Decision.DENY
    assert unverified.metadata["resolved_references"][0]["status"] == "unknown"
    assert verified.decision == Decision.ALLOW
    assert verified.metadata["resolved_references"][0]["resolver_id"] == "trusted-catalog"


def test_layered_policy_queries_are_tenant_scoped() -> None:
    seen: list[tuple[str, str]] = []

    class _TenantAwareLayered:
        def get_tool_capabilities(self, tenant_id: str):
            seen.append(("caps", tenant_id))
            return {}

        def get_sensitive_pattern(self, tenant_id: str):
            seen.append(("pattern", tenant_id))
            return None

    set_global_source(_TenantAwareLayered())  # type: ignore[arg-type]
    try:
        gate = Gate4Taint(GateConfig(options={
            "tool_capabilities_file": "policies/baseline/gate4_capabilities.yaml", "prefer_layered": True,
        }))
        result = gate.evaluate(GateContext(tool_name="echo", tenant_id="tenant-a"), GateStage.INBOUND)
    finally:
        set_global_source(None)

    assert result.decision == Decision.ALLOW
    assert seen == [("caps", "tenant-a"), ("pattern", "tenant-a")]


def test_reference_fields_are_schema_aware_not_arbitrary_argument_strings() -> None:
    result = _gate().evaluate(GateContext(
        tool_name="send_email",
        arguments={"to": "outside@example.test", "body": "reference cit-1001 is mentioned only as prose"},
    ), GateStage.INBOUND)

    assert result.decision == Decision.ALLOW
    assert result.metadata["resolved_references"] == []


def _envelope_payload(arguments: dict[str, object]) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "session_id": "session-1", "turn_id": "turn-1", "task_id": "task-1",
        "human_principal": "alice", "agent_id": "agent-1", "tenant_id": "tenant-a",
        "history_digest": "c" * 64, "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(), "nonce": "nonce-1",
        "tool_name": "send_email", "arguments_sha256": canonical_sha256(arguments),
        "key_id": "adapter-key-1",
        "sources": [{
            "source_id": "doc-1", "kind": "document", "locator_digest": "d" * 64,
            "content_digest": "e" * 64, "trust_state": "verified", "taint": "INTERNAL",
        }],
    }


def test_envelope_strictly_binds_tool_and_arguments() -> None:
    arguments = {"to": "ops@example.test", "body": "safe"}
    envelope = TrustedContextEnvelope.from_dict(_envelope_payload(arguments))

    envelope.validate(tool_name="send_email", arguments=arguments)
    with pytest.raises(ValueError, match="arguments binding mismatch"):
        envelope.validate(tool_name="send_email", arguments={"to": "outside@example.test", "body": "safe"})
    with pytest.raises(ValueError, match="tool binding mismatch"):
        envelope.validate(tool_name="post_url", arguments=arguments)


def test_envelope_hmac_rejects_forgery_wrong_key_and_tampering() -> None:
    arguments = {"to": "ops@example.test", "body": "safe"}
    signed = TrustedContextEnvelope.from_dict(_envelope_payload(arguments)).sign(b"trusted-adapter-key")

    assert signed.verify_signature({"adapter-key-1": b"trusted-adapter-key"})
    assert not signed.verify_signature({"adapter-key-1": b"wrong-key"})
    assert not signed.verify_signature({"other-key": b"trusted-adapter-key"})

    forged = TrustedContextEnvelope.from_dict({
        **_envelope_payload(arguments), "signature": signed.signature,
        "human_principal": "attacker",
    })
    assert not forged.verify_signature({"adapter-key-1": b"trusted-adapter-key"})


def test_envelope_rejects_missing_digests_and_expiry_without_timezone() -> None:
    payload = _envelope_payload({"to": "ops@example.test", "body": "safe"})
    payload["sources"] = [{"source_id": "doc-1", "kind": "document"}]
    with pytest.raises(ValueError, match="locator_digest"):
        TrustedContextEnvelope.from_dict(payload)

    payload = _envelope_payload({"to": "ops@example.test", "body": "safe"})
    payload["expires_at"] = "2026-01-01T00:00:00"
    envelope = TrustedContextEnvelope.from_dict(payload)
    with pytest.raises(ValueError, match="timezone"):
        envelope.validate(tool_name="send_email", arguments={"to": "ops@example.test", "body": "safe"})


def test_envelope_rejects_expired_signed_context() -> None:
    arguments = {"to": "ops@example.test", "body": "safe"}
    payload = _envelope_payload(arguments)
    payload["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    envelope = TrustedContextEnvelope.from_dict(payload).sign(b"trusted-adapter-key")
    assert envelope.verify_signature({"adapter-key-1": b"trusted-adapter-key"})
    with pytest.raises(ValueError, match="expired"):
        envelope.validate(tool_name="send_email", arguments=arguments)


def test_envelope_rejects_future_issue_time_and_excessive_lifetime() -> None:
    arguments = {"to": "ops@example.test", "body": "safe"}
    now = datetime.now(timezone.utc)
    payload = _envelope_payload(arguments)
    payload["issued_at"] = (now + timedelta(minutes=2)).isoformat()
    payload["expires_at"] = (now + timedelta(minutes=7)).isoformat()
    future = TrustedContextEnvelope.from_dict(payload)
    with pytest.raises(ValueError, match="issued in the future"):
        future.validate(
            tool_name="send_email",
            arguments=arguments,
            now=now,
        )

    payload = _envelope_payload(arguments)
    payload["issued_at"] = now.isoformat()
    payload["expires_at"] = (now + timedelta(minutes=16)).isoformat()
    excessive = TrustedContextEnvelope.from_dict(payload)
    with pytest.raises(ValueError, match="lifetime exceeds"):
        excessive.validate(
            tool_name="send_email",
            arguments=arguments,
            now=now,
        )
