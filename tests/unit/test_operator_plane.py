"""Regression coverage for the separate, non-GUI HITL operator plane."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from mcp import types as mtypes

from xa_guard.gates import GateStage
from xa_guard.gates.base import Gate
from xa_guard.identity import VerifiedIdentity
from xa_guard.pipeline import Pipeline, PipelineResult
from xa_guard.proxy.operator import (
    OperatorApprovalService,
    OperatorCredentialMiddleware,
    build_operator_server,
    operator_credential_from_context,
)
from xa_guard.proxy.pending import PendingApprovalStore
from xa_guard.proxy.upstream import _build_app, _build_streamable_http_asgi_app
from xa_guard.types import Decision, GateContext, GateResult


def _identity(
    human: str = "operator-alice", *, tenant: str = "tenant-a", roles: tuple[str, ...] = ("xa_guard.operator",)
) -> VerifiedIdentity:
    return VerifiedIdentity(
        human_principal=human,
        agent_id="operator-console",
        tenant_id=tenant,
        issuer="test",
        scopes=(), tools=(), data_domains=(), permissions=(), kid="test", jti_sha256="digest",
        roles=roles,
    )


def _pending_ctx(*, human: str = "requester-bob", agent: str = "office-agent", tenant: str = "tenant-a", trace_id: str = "pending-1") -> GateContext:
    return GateContext(
        trace_id=trace_id, tool_name="send_message", arguments={"body": "private", "api_key": "do-not-expose"},
        human_principal=human, agent_id=agent, tenant_id=tenant, final_decision=Decision.REQUIRE_APPROVAL,
    )


@dataclass
class _Approval:
    approver: str


class _AuditGate:
    def __init__(self) -> None:
        self.calls: list[GateContext] = []

    def __call__(self, ctx: GateContext, stage: object) -> GateResult:
        self.calls.append(ctx)
        return GateResult(gate_name="gate6", decision=Decision.ALLOW)


class _Pipeline:
    cfg = None

    def __init__(self) -> None:
        self.gate6 = _AuditGate()
        self.issued: list[tuple[GateContext, str, str]] = []
        self.rejected: list[tuple[GateContext, str, str]] = []
        self.resumed: list[GateContext] = []

    def issue_bound_approval(self, ctx: GateContext, *, approver: str, reason: str):
        self.issued.append((ctx, approver, reason))
        return _Approval(approver)

    async def run_after_approval(self, ctx: GateContext, executor):
        self.resumed.append(ctx)
        value = await executor(ctx)
        return PipelineResult(ctx, True, value, Decision.ALLOW, "allowed")

    async def reject_after_approval(self, ctx: GateContext, *, approver: str, reason: str):
        self.rejected.append((ctx, approver, reason))
        return PipelineResult(ctx, False, None, Decision.DENY, "rejected")


class _AgentPipeline(_Pipeline):
    async def run(self, ctx: GateContext, executor):
        del executor
        ctx.final_decision = Decision.REQUIRE_APPROVAL
        ctx.final_reason = "independent operator required"
        return PipelineResult(
            ctx,
            False,
            None,
            Decision.REQUIRE_APPROVAL,
            ctx.final_reason,
        )


class _Router:
    def list_tools(self):
        return [
            {
                "name": "send_message",
                "description": "send",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]

    async def call_tool(self, ctx: GateContext):
        return {"tool": ctx.tool_name}


class _DecisionGate(Gate):
    def __init__(
        self,
        name: str,
        decision: Decision = Decision.ALLOW,
        *,
        stages: tuple[GateStage, ...] = (GateStage.INBOUND,),
    ) -> None:
        super().__init__()
        self.name = name
        self.decision = decision
        self.supported_stages = stages

    def evaluate(
        self,
        ctx: GateContext,
        stage: GateStage = GateStage.INBOUND,
    ) -> GateResult:
        del ctx, stage
        return GateResult(gate_name=self.name, decision=self.decision)


async def _executor(ctx: GateContext) -> str:
    del ctx
    return "executed"


def _service(store: PendingApprovalStore, pipeline: _Pipeline | None = None):
    return OperatorApprovalService(
        pipeline=pipeline or _Pipeline(), pending=store, executor=_executor, credential="operator-secret"
    )


def test_operator_listing_is_tenant_scoped_and_redacts_arguments() -> None:
    store = PendingApprovalStore()
    store.add(_pending_ctx())
    store.add(_pending_ctx(tenant="tenant-b", trace_id="pending-2"))
    service = _service(store)

    result, items = service.list_pending(
        identity=_identity(), credential="operator-secret", tenant_id="tenant-a"
    )

    assert result.ok
    assert len(items) == 1
    assert items[0]["arguments"]["api_key"].startswith("[REDACTED]")
    assert items[0]["arguments_redacted"] is True
    assert "do-not-expose" not in str(items)


def test_operator_rejects_missing_credential_role_and_tenant_and_audits() -> None:
    store = PendingApprovalStore()
    store.add(_pending_ctx())
    pipeline = _Pipeline()
    service = _service(store, pipeline)

    missing = asyncio.run(service.decide(
        trace_id="pending-1", approve=True, reason="", identity=_identity(), credential="", tenant_id="tenant-a"
    ))
    role = asyncio.run(service.decide(
        trace_id="pending-1", approve=True, reason="", identity=_identity(roles=()), credential="operator-secret", tenant_id="tenant-a"
    ))
    tenant = asyncio.run(service.decide(
        trace_id="pending-1", approve=True, reason="", identity=_identity(tenant="tenant-b"), credential="operator-secret", tenant_id="tenant-b"
    ))

    assert not missing.ok and "credential" in missing.message
    assert not role.ok and "role" in role.message
    assert not tenant.ok and "tenant" in tenant.message
    assert len(store.list()) == 1
    assert len(pipeline.gate6.calls) == 3
    assert all(call.gate_results[-1].gate_name == "gate6" for call in pipeline.gate6.calls)


def test_operator_prevents_requester_or_agent_self_approval() -> None:
    for identity in (_identity("requester-bob"), _identity("operator-alice")):
        store = PendingApprovalStore()
        ctx = _pending_ctx()
        store.add(ctx)
        service = _service(store)
        if identity.human_principal == "operator-alice":
            identity = VerifiedIdentity(
                human_principal=identity.human_principal, agent_id="office-agent", tenant_id=identity.tenant_id,
                issuer=identity.issuer, scopes=(), tools=(), data_domains=(), permissions=(), kid="test", jti_sha256="digest", roles=identity.roles,
            )
        outcome = asyncio.run(service.decide(
            trace_id="pending-1", approve=True, reason="review", identity=identity, credential="operator-secret", tenant_id="tenant-a"
        ))
        assert not outcome.ok
        assert "self-approval" in outcome.message
        assert len(store.list()) == 1


def test_rejected_operator_attempt_cannot_poison_later_legitimate_approval() -> None:
    pipeline = Pipeline(
        gate1=_DecisionGate("gate1"),
        gate2=_DecisionGate("gate2", Decision.REQUIRE_APPROVAL),
        gate3=_DecisionGate("gate3"),
        gate4=_DecisionGate(
            "gate4",
            stages=(GateStage.INBOUND, GateStage.OUTBOUND),
        ),
        gate5=_DecisionGate("gate5"),
        gate6=_DecisionGate("gate6", stages=(GateStage.OUTBOUND,)),
    )
    executions: list[str] = []

    async def executor(ctx: GateContext) -> str:
        executions.append(ctx.trace_id)
        return "executed"

    ctx = _pending_ctx()
    assert asyncio.run(pipeline.run(ctx, executor)).final_decision == Decision.REQUIRE_APPROVAL
    store = PendingApprovalStore()
    store.add(ctx)
    service = OperatorApprovalService(
        pipeline=pipeline,
        pending=store,
        executor=executor,
        credential="operator-secret",
    )

    poisoned = asyncio.run(
        service.decide(
            trace_id=ctx.trace_id,
            approve=True,
            reason="self approval",
            identity=_identity("requester-bob"),
            credential="operator-secret",
            tenant_id="tenant-a",
        )
    )

    assert poisoned.ok is False
    assert ctx.final_decision == Decision.REQUIRE_APPROVAL
    assert len(store.list()) == 1
    assert executions == []

    legitimate = asyncio.run(
        service.decide(
            trace_id=ctx.trace_id,
            approve=True,
            reason="independent review",
            identity=_identity("dora"),
            credential="operator-secret",
            tenant_id="tenant-a",
        )
    )

    assert legitimate.ok is True
    assert executions == [ctx.trace_id]
    assert store.list() == []


def test_restart_recovery_with_history_requires_fresh_request(
    tmp_path,
) -> None:
    ledger = tmp_path / "pending.jsonl"
    ctx = _pending_ctx()
    ctx.session_history = [
        {"role": "user", "content": "history-body-must-not-persist"}
    ]
    PendingApprovalStore(ledger_path=ledger).add(ctx)
    ledger_text = ledger.read_text(encoding="utf-8")
    assert "history-body-must-not-persist" not in ledger_text

    recovered_store = PendingApprovalStore(ledger_path=ledger)
    recovered = recovered_store.list()[0]
    assert recovered.recovered_from_ledger is True
    assert recovered.requires_fresh_context is True
    pipeline = _Pipeline()
    service = _service(recovered_store, pipeline)

    result = asyncio.run(
        service.decide(
            trace_id=ctx.trace_id,
            approve=True,
            reason="reviewed after restart",
            identity=_identity("dora"),
            credential="operator-secret",
            tenant_id="tenant-a",
        )
    )

    assert result.ok is False
    assert "re-submit" in result.message
    assert pipeline.resumed == []
    assert pipeline.rejected[0][2] == (
        "pending_context_requires_rehydration_after_restart"
    )


def test_operator_uses_verified_identity_as_approver_and_bound_resume() -> None:
    store = PendingApprovalStore()
    store.add(_pending_ctx())
    pipeline = _Pipeline()
    service = _service(store, pipeline)

    outcome = asyncio.run(service.decide(
        trace_id="pending-1", approve=True, reason="approved by policy", identity=_identity(), credential="operator-secret", tenant_id="tenant-a"
    ))

    assert outcome.ok
    assert pipeline.issued[0][1] == "operator-alice"
    assert pipeline.issued[0][2] == "approved by policy"
    assert len(pipeline.resumed) == 1
    assert store.list() == []


def test_operator_mcp_server_has_only_operator_tools() -> None:
    store = PendingApprovalStore()
    server = build_operator_server(
        service=_service(store),
        identity_provider=_identity,
        credential_provider=lambda: "operator-secret",
    )
    handlers = getattr(server, "_tool_handlers", None)
    # The precise mcp internal registry differs by version; server construction
    # is the contract here, while service tests above enforce authorization.
    assert server.name == "xa-guard-operator"
    assert handlers is None or "xa_guard_approve_pending" not in str(handlers)

    listed = asyncio.run(
        server.request_handlers[mtypes.ListToolsRequest](
            mtypes.ListToolsRequest()
        )
    )
    assert {tool.name for tool in listed.root.tools} == {
        "xa_guard_operator_list_pending",
        "xa_guard_operator_decide",
    }
    assert all(
        "credential" not in tool.inputSchema.get("properties", {})
        for tool in listed.root.tools
    )


def test_operator_credential_header_is_request_local_and_not_body_data() -> None:
    captured: list[str] = []

    async def app(scope, receive, send):
        del scope, receive
        captured.append(operator_credential_from_context())
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = OperatorCredentialMiddleware(app)

    async def run() -> None:
        messages = [{"type": "http.request", "body": b"", "more_body": False}]

        async def receive():
            return messages.pop(0)

        async def send(_message):
            return None

        await middleware(
            {
                "type": "http",
                "headers": [
                    (b"x-xa-guard-operator-token", b"transport-secret")
                ],
            },
            receive,
            send,
        )

    asyncio.run(run())

    assert captured == ["transport-secret"]
    assert operator_credential_from_context() == ""


def test_agent_and_operator_planes_can_share_one_in_memory_pending_store() -> None:
    store = PendingApprovalStore()
    pipeline = _AgentPipeline()
    agent_server = _build_app(
        pipeline,
        _Router(),
        expose_operator_tools=False,
        allow_client_elicitation=False,
        pending_store=store,
    )
    handler = agent_server.request_handlers[mtypes.CallToolRequest]
    blocked = asyncio.run(
        handler(
            mtypes.CallToolRequest(
                params=mtypes.CallToolRequestParams(
                    name="send_message",
                    arguments={
                        "body": "review me",
                        "_xa_guard": {
                            "human_principal": "requester-bob",
                            "agent_id": "office-agent",
                            "tenant_id": "tenant-a",
                        },
                    },
                )
            )
        )
    )

    assert "独立 Operator 控制面" in blocked.root.content[0].text
    assert len(store.list()) == 1
    service = _service(store, pipeline)
    listed, items = service.list_pending(
        identity=_identity(),
        credential="operator-secret",
        tenant_id="tenant-a",
    )
    assert listed.ok
    assert len(items) == 1


def test_http_factory_mounts_separate_operator_manager_with_shared_store() -> None:
    app = _build_streamable_http_asgi_app(
        _AgentPipeline(),
        _Router(),
        host="127.0.0.1",
        port=3000,
    )
    route_paths = {getattr(route, "path", "") for route in app.routes}

    assert "/operator/mcp" in route_paths
    assert "/mcp" in route_paths
    assert app.state.operator_session_manager is not app.state.session_manager
    assert isinstance(app.state.pending_approval_store, PendingApprovalStore)


def test_dora_operator_drives_real_bound_revalidation_and_one_execution() -> None:
    pipeline = Pipeline(
        gate1=_DecisionGate("gate1"),
        gate2=_DecisionGate("gate2", Decision.REQUIRE_APPROVAL),
        gate3=_DecisionGate("gate3"),
        gate4=_DecisionGate(
            "gate4",
            stages=(GateStage.INBOUND, GateStage.OUTBOUND),
        ),
        gate5=_DecisionGate("gate5"),
        gate6=_DecisionGate(
            "gate6",
            stages=(GateStage.OUTBOUND,),
        ),
    )
    calls: list[str] = []

    async def executor(ctx: GateContext) -> dict[str, bool]:
        calls.append(ctx.trace_id)
        return {"executed": True}

    ctx = GateContext(
        trace_id="alice-request-1",
        tool_name="send_message",
        arguments={"to": "external", "body": "approved business text"},
        tenant_id="tenant-a",
        human_principal="alice",
        agent_id="office-agent",
        identity_verified=True,
        identity_issuer="test-issuer",
        identity_jti_sha256="request-jti",
        effect_class="external_write",
    )
    initial = asyncio.run(pipeline.run(ctx, executor))
    assert initial.final_decision == Decision.REQUIRE_APPROVAL
    assert calls == []

    store = PendingApprovalStore()
    store.add(ctx)
    service = OperatorApprovalService(
        pipeline=pipeline,
        pending=store,
        executor=executor,
        credential="operator-secret",
    )
    dora = _identity("dora")

    outcome = asyncio.run(
        service.decide(
            trace_id=ctx.trace_id,
            approve=True,
            reason="independent business owner review",
            identity=dora,
            credential="operator-secret",
            tenant_id="tenant-a",
        )
    )

    assert outcome.ok is True
    assert outcome.decision == Decision.ALLOW.value
    assert calls == [ctx.trace_id]
    assert ctx.approval is not None
    assert ctx.approval.approver == "dora"
    assert ctx.approval.request_identity
    assert ctx.approval.policy_bundle_sha
    assert ctx.approval.effect_class == "external_write"
