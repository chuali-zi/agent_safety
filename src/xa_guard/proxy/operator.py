"""Independent, non-GUI HITL operator plane.

This module deliberately has no dependency on the agent-facing proxy handlers.
The embedding process constructs it with the *same* ``PendingApprovalStore``
used by the agent plane, but exposes it on a distinct authenticated transport.
It never trusts an ``approver`` value supplied in a tool argument: the operator
identity is provided by the transport's already-verified identity middleware.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass
from hmac import compare_digest
from typing import Any, Callable

from mcp import types as mtypes
from mcp.server import Server

from xa_guard.gates import GateStage
from xa_guard.identity import VerifiedIdentity
from xa_guard.pipeline import Pipeline, ToolExecutor
from xa_guard.proxy.pending import PendingApprovalStore, arguments_are_redacted, redact_arguments
from xa_guard.types import Decision, GateContext, GateResult


log = logging.getLogger("xa_guard.proxy.operator")

DEFAULT_OPERATOR_ROLE = "xa_guard.operator"
_TOKEN_ENV = "XA_GUARD_APPROVAL_OPERATOR_TOKEN"


@dataclass(frozen=True)
class OperatorResult:
    """Deliberately small response surface; raw tool arguments/results stay off it."""

    ok: bool
    trace_id: str = ""
    decision: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "ok": self.ok,
            "trace_id": self.trace_id,
            "decision": self.decision,
            "message": self.message,
        }


IdentityProvider = Callable[[], VerifiedIdentity | None]
CredentialProvider = Callable[[], str]
_OPERATOR_CREDENTIAL: ContextVar[str] = ContextVar(
    "xa_guard_operator_credential",
    default="",
)


def operator_credential_from_context() -> str:
    """Return the transport credential without placing it in MCP arguments."""
    return _OPERATOR_CREDENTIAL.get()


class OperatorCredentialMiddleware:
    """Copy the dedicated operator header into a request-local context.

    The value is never added to the MCP request body, GateContext, pending
    ledger, response, or audit record.
    """

    def __init__(
        self,
        app: Any,
        *,
        header_name: bytes = b"x-xa-guard-operator-token",
    ) -> None:
        self.app = app
        self.header_name = header_name.lower()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        credential = ""
        if scope.get("type") == "http":
            for key, value in scope.get("headers", []):
                if bytes(key).lower() == self.header_name:
                    credential = bytes(value).decode("latin-1")
                    break
        token = _OPERATOR_CREDENTIAL.set(credential)
        try:
            await self.app(scope, receive, send)
        finally:
            _OPERATOR_CREDENTIAL.reset(token)


class OperatorApprovalService:
    """Authorise and resolve pending approvals on a dedicated operator plane.

    The caller must arrange transport authentication and pass a provider that
    returns an identity created by :mod:`xa_guard.identity`; a user-controlled
    JSON identity is intentionally not accepted by this API.
    """

    def __init__(
        self,
        *,
        pipeline: Pipeline,
        pending: PendingApprovalStore,
        executor: ToolExecutor,
        credential: str | None = None,
        required_role: str = DEFAULT_OPERATOR_ROLE,
    ) -> None:
        self.pipeline = pipeline
        self.pending = pending
        self.executor = executor
        # Empty / missing means fail closed.  Production wiring reads the
        # configured secret once at process start rather than accepting a
        # client-selected credential source.
        self.credential = credential if credential is not None else os.getenv(_TOKEN_ENV, "")
        self.required_role = required_role

    def list_pending(
        self,
        *,
        identity: VerifiedIdentity | None,
        credential: str,
        tenant_id: str,
    ) -> tuple[OperatorResult, list[dict[str, Any]]]:
        error = self._authorise(identity=identity, credential=credential, tenant_id=tenant_id)
        if error:
            self._audit_rejection(None, error, operator_identity=identity)
            return OperatorResult(False, decision=Decision.DENY.value, message=error), []
        assert identity is not None
        items: list[dict[str, Any]] = []
        for item in self.pending.list():
            ctx = item.ctx
            if ctx.tenant_id != identity.tenant_id:
                continue
            items.append(
                {
                    "trace_id": ctx.trace_id,
                    "tool_name": ctx.tool_name,
                    "arguments": redact_arguments(ctx.arguments, item.input_schema),
                    "arguments_redacted": arguments_are_redacted(
                        redact_arguments(ctx.arguments, item.input_schema)
                    ),
                    "created_at": item.created_at.isoformat(),
                    "expires_at": item.expires_at.isoformat(),
                    "final_reason": ctx.final_reason,
                    "risk_level": getattr(ctx.risk_level, "value", str(ctx.risk_level)),
                    "rule_hits": list(ctx.rule_hits),
                }
            )
        return OperatorResult(True, decision=Decision.ALLOW.value, message="pending approvals listed"), items

    async def decide(
        self,
        *,
        trace_id: str,
        approve: bool,
        reason: str,
        identity: VerifiedIdentity | None,
        credential: str,
        tenant_id: str,
    ) -> OperatorResult:
        error = self._authorise(identity=identity, credential=credential, tenant_id=tenant_id)
        if error:
            self._audit_rejection(
                None,
                error,
                trace_id=trace_id,
                operator_identity=identity,
            )
            return OperatorResult(False, trace_id=trace_id, decision=Decision.DENY.value, message=error)
        if not trace_id:
            error = "trace_id is required"
            self._audit_rejection(
                None,
                error,
                operator_identity=identity,
            )
            return OperatorResult(False, decision=Decision.DENY.value, message=error)
        assert identity is not None

        # Peek before consuming: an unauthorised approver must never be able to
        # remove somebody else's pending action merely by guessing a trace id.
        item = next((value for value in self.pending.list() if value.ctx.trace_id == trace_id), None)
        if item is None:
            error = "pending approval is missing or expired"
            self._audit_rejection(
                None,
                error,
                trace_id=trace_id,
                operator_identity=identity,
            )
            return OperatorResult(False, trace_id=trace_id, decision=Decision.DENY.value, message=error)
        ctx = item.ctx
        if ctx.tenant_id != identity.tenant_id:
            error = "operator tenant does not match pending approval tenant"
            self._audit_rejection(
                ctx,
                error,
                operator_identity=identity,
            )
            return OperatorResult(False, trace_id=trace_id, decision=Decision.DENY.value, message=error)
        if self._is_self_approval(identity, ctx):
            error = "separation of duty forbids self-approval"
            self._audit_rejection(
                ctx,
                error,
                operator_identity=identity,
            )
            return OperatorResult(False, trace_id=trace_id, decision=Decision.DENY.value, message=error)
        if not str(reason or "").strip():
            error = "operator decision reason is required"
            self._audit_rejection(
                ctx,
                error,
                operator_identity=identity,
            )
            return OperatorResult(
                False,
                trace_id=trace_id,
                decision=Decision.DENY.value,
                message=error,
            )

        consumed = self.pending.pop(trace_id, outcome="approved" if approve else "rejected")
        if consumed is None:  # concurrent operator consumed it after the peek
            error = "pending approval is missing or expired"
            self._audit_rejection(
                ctx,
                error,
                operator_identity=identity,
            )
            return OperatorResult(False, trace_id=trace_id, decision=Decision.DENY.value, message=error)
        ctx = consumed.ctx
        approver = identity.human_principal
        if not approve:
            await self.pipeline.reject_after_approval(ctx, approver=approver, reason=reason)
            return OperatorResult(True, trace_id=trace_id, decision=Decision.DENY.value, message="approval rejected")
        if consumed.recovered_from_ledger and consumed.requires_fresh_context:
            await self.pipeline.reject_after_approval(
                ctx,
                approver=approver,
                reason="pending_context_requires_rehydration_after_restart",
            )
            return OperatorResult(
                False,
                trace_id=trace_id,
                decision=Decision.DENY.value,
                message=(
                    "trusted identity, provenance, or history was not persisted; "
                    "re-submit the request after restart"
                ),
            )
        if arguments_are_redacted(ctx.arguments):
            await self.pipeline.reject_after_approval(
                ctx, approver=approver, reason="pending_arguments_redacted_after_restart"
            )
            return OperatorResult(
                False, trace_id=trace_id, decision=Decision.DENY.value,
                message="pending arguments were redacted after restart; re-submit the request",
            )
        ctx.approval = self.pipeline.issue_bound_approval(ctx, approver=approver, reason=reason)
        resumed = await self.pipeline.run_after_approval(ctx, self.executor)
        if not resumed.allowed:
            return OperatorResult(
                False, trace_id=trace_id, decision=resumed.final_decision.value,
                message="approval did not pass re-evaluation",
            )
        return OperatorResult(True, trace_id=trace_id, decision=Decision.ALLOW.value, message="approved and executed")

    def _authorise(
        self,
        *,
        identity: VerifiedIdentity | None,
        credential: str,
        tenant_id: str,
    ) -> str:
        if not self.credential:
            return "operator credential is not configured"
        if not credential or not compare_digest(credential, self.credential):
            return "operator credential is invalid"
        if identity is None:
            return "verified operator identity is required"
        if not identity.human_principal or not identity.agent_id or not identity.tenant_id:
            return "verified operator identity is incomplete"
        if self.required_role not in set(identity.roles):
            return "operator identity lacks required role"
        if not tenant_id or tenant_id != identity.tenant_id:
            return "operator tenant is missing or conflicts with verified identity"
        return ""

    @staticmethod
    def _is_self_approval(identity: VerifiedIdentity, ctx: GateContext) -> bool:
        operator_principals = {identity.human_principal, identity.agent_id}
        requester_principals = {ctx.human_principal, ctx.agent_id}
        return bool({value for value in operator_principals & requester_principals if value})

    def _audit_rejection(
        self,
        ctx: GateContext | None,
        reason: str,
        *,
        trace_id: str = "",
        operator_identity: VerifiedIdentity | None = None,
    ) -> None:
        """Best-effort Gate6 audit without mutating the pending request.

        ``PendingApprovalStore`` retains the original ``GateContext`` object.
        Appending a rejection result to that object would change its terminal
        decision from REQUIRE_APPROVAL to DENY and let an unauthorised attempt
        poison a later legitimate review.  A separate, argument-free context
        also keeps the control-plane audit from copying business payloads.
        """
        audit_ctx = GateContext(
            trace_id=(ctx.trace_id if ctx is not None else trace_id)
            or GateContext().trace_id,
            tool_name="xa_guard_operator_approval",
            arguments={},
            tenant_id=(
                operator_identity.tenant_id
                if operator_identity is not None
                else ctx.tenant_id
                if ctx is not None
                else ""
            ),
            human_principal=(
                operator_identity.human_principal
                if operator_identity is not None
                else ""
            ),
            agent_id=(
                operator_identity.agent_id
                if operator_identity is not None
                else ""
            ),
            task_id=ctx.task_id if ctx is not None else "",
            identity_verified=operator_identity is not None,
            identity_issuer=(
                operator_identity.issuer
                if operator_identity is not None
                else ""
            ),
            identity_kid=(
                operator_identity.kid
                if operator_identity is not None
                else ""
            ),
            identity_jti_sha256=(
                operator_identity.jti_sha256
                if operator_identity is not None
                else ""
            ),
            identity_scopes=(
                list(operator_identity.scopes)
                if operator_identity is not None
                else []
            ),
        )
        audit_ctx.append(
            GateResult(
                gate_name="operator_plane",
                decision=Decision.DENY,
                risks=[reason],
                metadata={
                    "operator_plane": "independent",
                    "rejection_reason": reason,
                    "pending_tool_name": ctx.tool_name if ctx is not None else "",
                    "pending_requester_sha256": (
                        hashlib.sha256(
                            (
                                f"{ctx.human_principal}\x00{ctx.agent_id}"
                            ).encode("utf-8")
                        ).hexdigest()
                        if ctx is not None
                        else ""
                    ),
                },
            )
        )
        try:
            audit = getattr(self.pipeline, "_audit_async", None)
            # This method is synchronous so it cannot await an async gate6
            # safely. The standard Gate6 implementation is synchronous; leave
            # a recorded context result even if an embedding uses async Gate6.
            if audit is None:
                result = self.pipeline.gate6(audit_ctx, GateStage.OUTBOUND)
                audit_ctx.append(result)
            else:
                result = self.pipeline.gate6(audit_ctx, GateStage.OUTBOUND)
                audit_ctx.append(result)
        except Exception:
            log.exception("operator-plane rejection audit sink failed")


def build_operator_server(
    *,
    service: OperatorApprovalService,
    identity_provider: IdentityProvider,
    credential_provider: CredentialProvider = operator_credential_from_context,
) -> Server:
    """Build a separate MCP server for an authenticated operator transport.

    The embedding must mount/run this server separately from the agent server
    and bind ``identity_provider`` to verified transport authentication.
    """
    app = Server("xa-guard-operator")

    @app.list_tools()
    async def _list_tools() -> list[mtypes.Tool]:
        return [
            mtypes.Tool(
                name="xa_guard_operator_list_pending",
                description="List redacted HITL approvals for the verified operator tenant.",
                inputSchema={
                    "type": "object",
                    "properties": {"tenant_id": {"type": "string"}},
                    "required": ["tenant_id"],
                    "additionalProperties": False,
                },
            ),
            mtypes.Tool(
                name="xa_guard_operator_decide",
                description="Approve or reject a pending HITL request on the independent operator plane.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "trace_id": {"type": "string"},
                        "approve": {"type": "boolean"},
                        "reason": {"type": "string"},
                        "tenant_id": {"type": "string"},
                    },
                    "required": ["trace_id", "approve", "reason", "tenant_id"],
                    "additionalProperties": False,
                },
            ),
        ]

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[mtypes.TextContent]:
        arguments = arguments or {}
        identity = identity_provider()
        credential = credential_provider()
        tenant_id = str(arguments.get("tenant_id") or "")
        if name == "xa_guard_operator_list_pending":
            result, items = service.list_pending(identity=identity, credential=credential, tenant_id=tenant_id)
            payload: dict[str, Any] = result.to_dict()
            if result.ok:
                payload["pending_approvals"] = items
            return [mtypes.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, sort_keys=True))]
        if name == "xa_guard_operator_decide":
            result = await service.decide(
                trace_id=str(arguments.get("trace_id") or ""),
                approve=bool(arguments.get("approve")),
                reason=str(arguments.get("reason") or ""),
                identity=identity,
                credential=credential,
                tenant_id=tenant_id,
            )
            return [mtypes.TextContent(type="text", text=json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))]
        service._audit_rejection(
            None,
            "operator tool is unknown",
            operator_identity=identity,
        )
        return [mtypes.TextContent(type="text", text=json.dumps(OperatorResult(False, decision=Decision.DENY.value, message="unknown operator tool").to_dict()))]

    return app
