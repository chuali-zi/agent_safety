"""Focused non-GUI regression tests for the P0 approval and MCP boundaries."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from mcp import types as mtypes

from xa_guard.gates import GateStage
from xa_guard.gates.base import Gate
from xa_guard.pipeline import Pipeline, PipelineResult
from xa_guard.provenance import (
    ResolutionStatus,
    ResolvedReference,
    TrustedContextEnvelope,
    canonical_sha256,
)
from xa_guard.proxy import upstream
from xa_guard.proxy.upstream import _build_app, _ctx_with_governance
from xa_guard.types import Decision, GateContext, GateResult, InputSource, TaintLabel


class _Gate(Gate):
    def __init__(self, name: str, decision: Decision = Decision.ALLOW) -> None:
        super().__init__()
        self.name = name
        self.decision = decision

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        del ctx, stage
        return GateResult(gate_name=self.name, decision=self.decision)


class _TaintGate(_Gate):
    def __init__(self, labels: list[TaintLabel]) -> None:
        super().__init__("gate4")
        self.labels = labels
        self.calls = 0

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        del ctx
        if stage == GateStage.OUTBOUND:
            return GateResult(gate_name=self.name, decision=Decision.ALLOW)
        label = self.labels[min(self.calls, len(self.labels) - 1)]
        self.calls += 1
        return GateResult(
            gate_name=self.name,
            decision=Decision.ALLOW,
            metadata={"taint": label.value},
        )


class _SecondPassDenyGate(_Gate):
    def __init__(self) -> None:
        super().__init__("gate3")
        self.calls = 0
        self.rules = [SimpleNamespace(id="stable-policy", predicate="true", enforce="allow", triggers=[])]

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        del ctx, stage
        self.calls += 1
        return GateResult(
            gate_name=self.name,
            decision=Decision.ALLOW if self.calls == 1 else Decision.DENY,
            risks=[] if self.calls == 1 else ["policy changed at second evaluation"],
        )


def _provenance(task_id: str = "task-1") -> TrustedContextEnvelope:
    return TrustedContextEnvelope(
        schema_version="1.0", session_id="session-1", turn_id="turn-1", task_id=task_id,
        human_principal="alice", agent_id="office-agent", tenant_id="tenant-a",
        history_digest=canonical_sha256([{"role": "user", "content": "please proceed"}]),
        issued_at="2026-07-30T00:00:00Z", expires_at="2099-07-30T00:00:00Z",
        nonce="provenance-nonce", tool_name="red_operation", arguments_sha256=canonical_sha256({"cmd": "safe"}),
        key_id="test", signature="not-used-by-direct-pipeline-test",
    )


def _pipeline(*, taints: list[TaintLabel] | None = None, gate3: Gate | None = None) -> Pipeline:
    return Pipeline(
        gate1=_Gate("gate1"),
        gate2=_Gate("gate2", Decision.REQUIRE_APPROVAL),
        gate3=gate3 or _Gate("gate3"),
        gate4=_TaintGate(taints or [TaintLabel.INTERNAL]),
        gate5=_Gate("gate5"),
        gate6=_Gate("gate6"),
    )


def _ctx() -> GateContext:
    history = [{"role": "user", "content": "please proceed"}]
    return GateContext(
        tool_name="red_operation", arguments={"cmd": "safe"}, human_principal="alice",
        agent_id="office-agent", tenant_id="tenant-a", session_history=history,
        input_sources=[InputSource.USER, InputSource.DOCUMENT], provenance=_provenance(),
        provenance_verified=True, effect_class="external_write",
    )


async def _executor(_ctx: GateContext) -> dict[str, bool]:
    return {"executed": True}


def _blocked_with_bound_approval(pipe: Pipeline) -> GateContext:
    ctx = _ctx()
    first = asyncio.run(pipe.run(ctx, _executor))
    assert first.final_decision == Decision.REQUIRE_APPROVAL
    ctx.approval = pipe.issue_bound_approval(ctx, approver="independent-reviewer")
    return ctx


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda ctx, pipe: setattr(ctx, "human_principal", "mallory"), "request_identity_mismatch"),
        (lambda ctx, pipe: setattr(ctx, "tenant_id", "tenant-b"), "tenant_id_mismatch"),
        (lambda ctx, pipe: setattr(ctx, "session_history", [{"role": "user", "content": "changed"}]), "history_digest_mismatch"),
        (lambda ctx, pipe: setattr(ctx, "provenance", replace(ctx.provenance, task_id="task-2")), "provenance_digest_mismatch"),
        (lambda ctx, pipe: setattr(ctx, "taint", TaintLabel.CONFIDENTIAL), "taint_mismatch"),
        (lambda ctx, pipe: setattr(ctx, "effect_class", "privileged_execute"), "effect_class_mismatch"),
        (lambda ctx, pipe: setattr(pipe.gate3, "rules", [SimpleNamespace(id="new", predicate="false", enforce="deny", triggers=[])]), "policy_bundle_sha_mismatch"),
    ],
)
def test_bound_approval_rejects_every_context_drift(change, expected):
    pipe = _pipeline()
    ctx = _blocked_with_bound_approval(pipe)
    change(ctx, pipe)

    result = asyncio.run(pipe.run_after_approval(ctx, _executor))

    assert result.allowed is False
    assert result.final_decision == Decision.DENY
    assert expected in result.final_reason


def test_second_evaluation_rejects_taint_drift_before_executor_and_consumption():
    calls: list[bool] = []

    async def executor(_ctx: GateContext) -> None:
        calls.append(True)

    pipe = _pipeline(taints=[TaintLabel.INTERNAL, TaintLabel.CONFIDENTIAL])
    ctx = _blocked_with_bound_approval(pipe)
    result = asyncio.run(pipe.run_after_approval(ctx, executor))

    assert result.final_decision == Decision.DENY
    assert "taint_mismatch" in result.final_reason
    assert calls == []


def test_second_evaluation_rechecks_policy_and_blocks_without_executing():
    calls: list[bool] = []

    async def executor(_ctx: GateContext) -> None:
        calls.append(True)

    gate3 = _SecondPassDenyGate()
    pipe = _pipeline(gate3=gate3)
    ctx = _blocked_with_bound_approval(pipe)
    result = asyncio.run(pipe.run_after_approval(ctx, executor))

    assert result.final_decision == Decision.DENY
    assert "approval_revalidation_denied" in result.final_reason
    assert calls == []


def test_expired_provenance_cannot_resume_under_still_valid_approval():
    calls: list[bool] = []

    async def executor(_ctx: GateContext) -> None:
        calls.append(True)

    pipe = _pipeline()
    ctx = _ctx()
    ctx.provenance = replace(
        ctx.provenance,
        issued_at="2026-07-29T00:00:00Z",
        expires_at="2026-07-29T00:05:00Z",
    )
    assert asyncio.run(pipe.run(ctx, executor)).final_decision == Decision.REQUIRE_APPROVAL
    ctx.approval = pipe.issue_bound_approval(
        ctx,
        approver="independent-reviewer",
    )

    result = asyncio.run(pipe.run_after_approval(ctx, executor))

    assert result.allowed is False
    assert result.final_decision == Decision.DENY
    assert "expired before approval" in result.final_reason
    assert calls == []


def test_bound_approval_token_cannot_be_replayed_after_a_successful_resume():
    first_pipe = _pipeline()
    first_ctx = _blocked_with_bound_approval(first_pipe)
    approval = first_ctx.approval
    assert asyncio.run(first_pipe.run_after_approval(first_ctx, _executor)).allowed is True

    replay_pipe = _pipeline()
    replay_ctx = _ctx()
    replay_ctx.trace_id = first_ctx.trace_id
    assert asyncio.run(replay_pipe.run(replay_ctx, _executor)).final_decision == Decision.REQUIRE_APPROVAL
    replay_ctx.approval = approval
    replayed = asyncio.run(replay_pipe.run_after_approval(replay_ctx, _executor))

    assert replayed.allowed is False
    assert replayed.final_decision == Decision.DENY
    assert "approval_token_replay" in replayed.final_reason


class _ApprovalPipeline:
    """Tiny protocol-compatible pipeline for upstream surface checks."""

    cfg = None

    async def run(self, ctx: GateContext, executor):
        del executor
        ctx.final_decision = Decision.REQUIRE_APPROVAL
        ctx.final_reason = "approval required"
        return PipelineResult(ctx, False, None, Decision.REQUIRE_APPROVAL, ctx.final_reason)

    async def run_after_approval(self, ctx: GateContext, executor):
        value = await executor(ctx)
        return PipelineResult(ctx, True, value, Decision.ALLOW, "approved")

    async def reject_after_approval(self, ctx: GateContext, *, approver="", reason=""):
        del approver, reason
        ctx.final_decision = Decision.DENY
        return PipelineResult(ctx, False, None, Decision.DENY, "rejected")


class _Router:
    def list_tools(self):
        return [{"name": "red_operation", "description": "test", "inputSchema": {"type": "object"}}]

    async def call_tool(self, ctx: GateContext):
        return {"tool": ctx.tool_name}


def _call_handler(app, name: str, arguments: dict):
    handler = app.request_handlers[mtypes.CallToolRequest]
    return asyncio.run(handler(mtypes.CallToolRequest(params=mtypes.CallToolRequestParams(name=name, arguments=arguments))))


def test_production_agent_plane_hides_operator_tools_and_disables_client_elicitation(monkeypatch, tmp_path):
    monkeypatch.setenv("XA_GUARD_PENDING_APPROVAL_STORE", str(tmp_path / "pending.jsonl"))
    elicited: list[bool] = []

    async def should_not_elicit(*_args, **_kwargs):
        elicited.append(True)
        return upstream._ApprovalOutcome(approved=True, approver="client")

    monkeypatch.setattr(upstream, "_request_hitl_approval", should_not_elicit)
    app = _build_app(
        _ApprovalPipeline(), _Router(), expose_operator_tools=False, allow_client_elicitation=False,
    )

    listed = asyncio.run(app.request_handlers[mtypes.ListToolsRequest](mtypes.ListToolsRequest()))
    names = {tool.name for tool in listed.root.tools}
    hidden = _call_handler(app, "xa_guard_approve_pending", {"trace_id": "x", "approve": True})
    blocked = _call_handler(app, "red_operation", {"cmd": "safe"})

    assert "xa_guard_approve_pending" not in names
    assert "xa_guard_list_pending_approvals" not in names
    assert "operator control tools are unavailable" in hidden.root.content[0].text
    assert "独立 Operator 控制面" in blocked.root.content[0].text
    assert elicited == []


def test_explicit_test_mode_keeps_legacy_operator_tools_visible():
    app = _build_app(_ApprovalPipeline(), _Router(), expose_operator_tools=True, allow_client_elicitation=True)
    listed = asyncio.run(app.request_handlers[mtypes.ListToolsRequest](mtypes.ListToolsRequest()))
    names = {tool.name for tool in listed.root.tools}

    assert "xa_guard_approve_pending" in names
    assert "xa_guard_list_pending_approvals" in names


def test_unsigned_ordinary_mcp_context_is_explicitly_unknown_not_user_trusted():
    ctx = _ctx_with_governance("read_status", {}, {})

    assert ctx.provenance is None
    assert ctx.provenance_verified is False
    assert ctx.input_sources == [InputSource.UNKNOWN]


def test_signed_reference_reason_survives_wire_parsing_and_signature_verification():
    envelope = replace(
        _provenance(),
        resolved_references=(
            ResolvedReference(
                reference_id="record-1", status=ResolutionStatus.FORBIDDEN,
                reason="tenant boundary", resolver_id="test-resolver",
            ),
        ),
        key_id="key-1",
    ).sign(b"unit-test-key")
    raw = {**envelope.unsigned_payload(), "signature": envelope.signature}

    parsed = TrustedContextEnvelope.from_dict(raw)

    assert parsed.resolved_references[0].reason == "tenant boundary"
    assert parsed.verify_signature({"key-1": b"unit-test-key"}) is True
