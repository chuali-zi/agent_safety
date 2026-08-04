from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from mcp import types as mtypes

from xa_guard.config import GateConfig, XAGuardConfig
from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.gates.gate2_plan import Gate2Plan
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.gates.gate5_sandbox import Gate5Sandbox
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.pipeline import Pipeline
from xa_guard.provenance import (
    ProvenanceSource,
    ResolutionStatus,
    ResolvedReference,
    TrustState,
    TrustedContextEnvelope,
    canonical_sha256,
)
from xa_guard.proxy.upstream import _build_app
from xa_guard.types import TaintLabel


class _Router:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "send_message",
                "description": "Send a message across the external boundary.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "content": {"type": "string"},
                        "sources": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            }
        ]

    async def call_tool(self, ctx):
        self.calls.append((ctx.tool_name, dict(ctx.arguments)))
        return {"delivered": True}


def _pipeline(tmp_path: Path) -> Pipeline:
    capability_file = tmp_path / "capabilities.yaml"
    capability_file.write_text(
        yaml.safe_dump(
            {
                "tools": [
                    {
                        "tool_name": "send_message",
                        "capabilities": ["NETWORK_EXTERNAL", "NOTIFY"],
                        "input_max_taint": "PUBLIC",
                        "output_taint": "PUBLIC",
                        "risk_level": "green",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    cfg = XAGuardConfig()
    return Pipeline(
        gate1=Gate1Input(cfg.gate("gate1")),
        gate2=Gate2Plan(
            GateConfig(
                enabled=True,
                options={"default_risk": "green"},
            )
        ),
        gate3=Gate3Policy(cfg.gate("gate3")),
        gate4=Gate4Taint(
            GateConfig(
                enabled=True,
                options={"tool_capabilities_file": str(capability_file)},
            )
        ),
        gate5=Gate5Sandbox(GateConfig(enabled=False)),
        gate6=Gate6Audit(
            GateConfig(
                enabled=True,
                options={
                    "audit_dir": str(tmp_path / "audit"),
                    "hash_algo": "sha256",
                },
            )
        ),
        cfg=cfg,
    )


def _signed_arguments(
    *,
    secret: bytes,
    reference: ResolvedReference | None,
    nonce: str | None = None,
) -> dict:
    arguments = {
        "to": "external-reviewer",
        "content": "Please review the referenced item.",
        "sources": [
            reference.reference_id if reference is not None else "unknown-item"
        ],
    }
    now = datetime.now(timezone.utc)
    envelope = TrustedContextEnvelope(
        schema_version="1.0",
        session_id="mcp-integration-session",
        turn_id="turn-1",
        task_id="d1-reference-egress",
        human_principal="requester-alice",
        agent_id="reference-office-agent",
        tenant_id="tenant-a",
        history_digest=canonical_sha256([]),
        sources=(
            ProvenanceSource(
                source_id="user-task",
                kind="user",
                locator_digest="a" * 64,
                content_digest="b" * 64,
                trust_state=TrustState.VERIFIED,
                taint=TaintLabel.PUBLIC,
            ),
        ),
        resolved_references=(reference,) if reference is not None else (),
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
        nonce=nonce or uuid.uuid4().hex,
        tool_name="send_message",
        arguments_sha256=canonical_sha256(arguments),
        key_id="integration-key",
    ).sign(secret)
    return {
        **arguments,
        "_xa_guard": {
            "human_principal": envelope.human_principal,
            "agent_id": envelope.agent_id,
            "tenant_id": envelope.tenant_id,
            "session_history": [],
            "provenance": {
                **envelope.unsigned_payload(),
                "signature": envelope.signature,
            },
        },
    }


def _call(app, arguments: dict):
    handler = app.request_handlers[mtypes.CallToolRequest]
    request = mtypes.CallToolRequest(
        params=mtypes.CallToolRequestParams(
            name="send_message",
            arguments=arguments,
        )
    )
    return asyncio.run(handler(request))


def _audit_record(tmp_path: Path) -> dict:
    rows = (tmp_path / "audit" / "audit.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    return json.loads(rows[-1])


def test_verified_confidential_reference_is_denied_before_downstream(
    tmp_path: Path,
    monkeypatch,
) -> None:
    secret = b"integration-provenance-secret"
    monkeypatch.setenv("XA_GUARD_PROVENANCE_HMAC_SECRET", secret.decode())
    monkeypatch.setenv("XA_GUARD_PROVENANCE_HMAC_KEY_ID", "integration-key")
    router = _Router()
    app = _build_app(
        _pipeline(tmp_path),
        router,
        expose_operator_tools=False,
        allow_client_elicitation=False,
    )
    reference = ResolvedReference(
        reference_id="contractor-roster",
        status=ResolutionStatus.RESOLVED,
        classification=TaintLabel.CONFIDENTIAL,
        taint=TaintLabel.CONFIDENTIAL,
        asset_digest="c" * 64,
        resolver_id="oar-world-v1",
    )

    result = _call(
        app,
        _signed_arguments(secret=secret, reference=reference),
    )
    audit = _audit_record(tmp_path)

    assert "XA-Guard 已拦截" in result.root.content[0].text
    assert router.calls == []
    assert audit["gen_ai.decision.final"] == "deny"
    assert audit["gen_ai.provenance.verified"] is True
    assert audit["gen_ai.provenance.resolved_references"][0][
        "classification"
    ] == "CONFIDENTIAL"


def test_verified_public_reference_preserves_safe_external_utility(
    tmp_path: Path,
    monkeypatch,
) -> None:
    secret = b"integration-provenance-secret"
    monkeypatch.setenv("XA_GUARD_PROVENANCE_HMAC_SECRET", secret.decode())
    monkeypatch.setenv("XA_GUARD_PROVENANCE_HMAC_KEY_ID", "integration-key")
    router = _Router()
    app = _build_app(
        _pipeline(tmp_path),
        router,
        expose_operator_tools=False,
        allow_client_elicitation=False,
    )
    reference = ResolvedReference(
        reference_id="public-brochure",
        status=ResolutionStatus.RESOLVED,
        classification=TaintLabel.PUBLIC,
        taint=TaintLabel.PUBLIC,
        asset_digest="d" * 64,
        resolver_id="oar-world-v1",
    )

    result = _call(
        app,
        _signed_arguments(secret=secret, reference=reference),
    )
    audit = _audit_record(tmp_path)

    assert "delivered" in result.root.content[0].text
    assert router.calls == [
        (
            "send_message",
            {
                "to": "external-reviewer",
                "content": "Please review the referenced item.",
                "sources": ["public-brochure"],
            },
        )
    ]
    assert audit["gen_ai.decision.final"] == "allow"
    assert audit["gen_ai.provenance.verified"] is True


def test_unknown_or_tampered_reference_context_fails_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    secret = b"integration-provenance-secret"
    monkeypatch.setenv("XA_GUARD_PROVENANCE_HMAC_SECRET", secret.decode())
    monkeypatch.setenv("XA_GUARD_PROVENANCE_HMAC_KEY_ID", "integration-key")
    router = _Router()
    app = _build_app(
        _pipeline(tmp_path),
        router,
        expose_operator_tools=False,
        allow_client_elicitation=False,
    )

    unknown = _call(
        app,
        _signed_arguments(secret=secret, reference=None),
    )
    tampered_arguments = _signed_arguments(
        secret=secret,
        reference=ResolvedReference(
            reference_id="public-brochure",
            status=ResolutionStatus.RESOLVED,
            asset_digest="e" * 64,
            resolver_id="oar-world-v1",
        ),
    )
    tampered_arguments["content"] = "changed after signing"
    tampered = _call(app, tampered_arguments)

    assert "XA-Guard 已拦截" in unknown.root.content[0].text
    assert "XA-Guard 已拦截" in tampered.root.content[0].text
    assert router.calls == []
