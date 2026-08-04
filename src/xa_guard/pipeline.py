"""6 关卡 pipeline 编排。

调用顺序（产品架构 §3.2）：
    inbound:  gate1 → gate2 → gate4(in) → gate3 → gate5
    [downstream tool execution]
    outbound: gate4(out) → gate6(audit)

Gate1 输入攻击立即短路；Gate2/Gate4/Gate3 属于同一轮执行前决策聚合，
先让 policy deny 覆盖 HITL require_approval，再进入 Gate5 / executor。
WARN 累积。每关卡 latency_ms 写入 GateResult，全程 trace 由 gate6 落审计。
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from xa_guard.config import XAGuardConfig
from xa_guard.gates import GateStage
from xa_guard.gates.base import Gate
from xa_guard.governance import GovernanceEnforcer
from xa_guard.provenance import (
    PROVENANCE_CLOCK_SKEW_SECONDS,
    canonical_sha256,
)
from xa_guard.types import Approval, Decision, GateContext, GateResult, RiskLevel, TaintLabel

log = logging.getLogger("xa_guard.pipeline")

ToolExecutor = Callable[[GateContext], Awaitable[object]]


def _sync_ctx_from_result(ctx: GateContext, result: GateResult) -> None:
    """把 gate result.metadata 中的 risk_level / taint 同步到 ctx。

    gate2 决定 risk_level，gate3 的 predicate 依赖 ctx.risk_level；
    gate4 决定 taint，下游同理。
    """
    rl = result.metadata.get("risk_level")
    if rl is not None:
        try:
            ctx.risk_level = RiskLevel(rl) if not isinstance(rl, RiskLevel) else rl
        except ValueError:
            pass
    tt = result.metadata.get("taint")
    if tt is None:
        tt = result.metadata.get("output_taint")
    if tt is not None:
        try:
            ctx.taint = TaintLabel(tt) if not isinstance(tt, TaintLabel) else tt
        except ValueError:
            pass


@dataclass
class PipelineResult:
    ctx: GateContext
    allowed: bool
    tool_result: object | None
    final_decision: Decision
    final_reason: str


class Pipeline:
    """6 关卡编排器。pipeline 不知道关卡内部细节，只按顺序串。"""

    def __init__(
        self,
        gate1: Gate,
        gate2: Gate,
        gate3: Gate,
        gate4: Gate,
        gate5: Gate,
        gate6: Gate,
        cfg: XAGuardConfig | None = None,
        governance: GovernanceEnforcer | None = None,
    ) -> None:
        self.gate1 = gate1
        self.gate2 = gate2
        self.gate3 = gate3
        self.gate4 = gate4
        self.gate5 = gate5
        self.gate6 = gate6
        self.cfg = cfg
        self.governance = governance

    def _policy_state_sha(self, ctx: GateContext) -> str:
        """Bind approvals to the effective policy/governance state, not a label."""
        layered_sha = ""
        try:
            from xa_guard.policy.layered import get_global_source

            source = get_global_source()
            if source is not None:
                layered_sha = source.effective_bundle_sha(ctx.tenant_id)
        except (AttributeError, RuntimeError):
            layered_sha = ""
        rules = []
        for rule in getattr(self.gate3, "rules", []) or []:
            rules.append(
                {
                    "id": getattr(rule, "id", ""),
                    "predicate": getattr(rule, "predicate", ""),
                    "enforce": str(getattr(rule, "enforce", "")),
                    "triggers": list(getattr(rule, "triggers", []) or []),
                }
            )
        registry = getattr(self.governance, "registry", None)
        if registry is not None and is_dataclass(registry):
            governance_state: object = asdict(registry)
        else:
            governance_state = {}
        return canonical_sha256(
            {
                "layered_bundle_sha": layered_sha,
                "legacy_gate3_rules": rules,
                "governance": governance_state,
            }
        )

    def approval_bindings(self, ctx: GateContext) -> dict[str, str]:
        """Canonical bindings shared by every production approval issuer/resume."""
        provenance = getattr(ctx, "provenance", None)
        provenance_verified = bool(getattr(ctx, "provenance_verified", False))
        if provenance_verified and provenance is not None:
            provenance_digest = canonical_sha256(provenance.unsigned_payload())
        else:
            provenance_digest = canonical_sha256(
                {
                    "verified": False,
                    "input_sources": [
                        str(getattr(value, "value", value)) for value in ctx.input_sources
                    ],
                }
            )
        identity_digest = canonical_sha256(
            {
                "verified": ctx.identity_verified,
                "issuer": ctx.identity_issuer,
                "kid": ctx.identity_kid,
                "jti_sha256": ctx.identity_jti_sha256,
                "human_principal": ctx.human_principal,
                "agent_id": ctx.agent_id,
            }
        )
        return {
            "request_identity": identity_digest,
            "tenant_id": ctx.tenant_id or "__default__",
            "provenance_digest": provenance_digest,
            "history_digest": canonical_sha256(ctx.session_history),
            "taint": ctx.taint.value,
            "policy_bundle_sha": self._policy_state_sha(ctx),
            "effect_class": Gate.effect_class(ctx),
        }

    @staticmethod
    def _provenance_revalidation_error(ctx: GateContext) -> str:
        """Recheck freshness and request bindings for an in-memory HITL resume.

        The ingress adapter already verified the immutable envelope MAC and
        consumed its nonce.  Re-consuming that nonce here would reject every
        legitimate resume, so this step instead proves that the same signed
        envelope remains fresh and still matches the current request, history,
        and verified identity.  The approval token separately binds the whole
        unsigned envelope digest.
        """
        if not ctx.provenance_verified:
            return ""
        provenance = ctx.provenance
        if provenance is None:
            return "verified provenance envelope is missing"
        try:
            if not provenance.tool_name or provenance.tool_name != ctx.tool_name:
                raise ValueError("provenance tool binding mismatch")
            if (
                not provenance.arguments_sha256
                or provenance.arguments_sha256 != canonical_sha256(ctx.arguments)
            ):
                raise ValueError("provenance arguments binding mismatch")
            if provenance.history_digest != canonical_sha256(ctx.session_history):
                raise ValueError("provenance history digest mismatch")
            identity_bindings = {
                "human_principal": ctx.human_principal,
                "agent_id": ctx.agent_id,
                "tenant_id": ctx.tenant_id,
            }
            for field, expected in identity_bindings.items():
                if str(getattr(provenance, field)) != str(expected):
                    raise ValueError(f"provenance {field} binding mismatch")

            now = datetime.now(timezone.utc)
            issued = datetime.fromisoformat(
                provenance.issued_at.replace("Z", "+00:00")
            )
            expiry = datetime.fromisoformat(
                provenance.expires_at.replace("Z", "+00:00")
            )
            if issued.tzinfo is None or expiry.tzinfo is None:
                raise ValueError("provenance timestamps require timezone")
            if now >= expiry:
                raise ValueError("provenance envelope expired before approval")
            if issued > now + timedelta(seconds=PROVENANCE_CLOCK_SKEW_SECONDS):
                raise ValueError("provenance envelope issued in the future")
        except (AttributeError, TypeError, ValueError) as exc:
            return str(exc)
        return ""

    async def _deny_invalid_resumed_provenance(
        self,
        ctx: GateContext,
    ) -> PipelineResult | None:
        error = self._provenance_revalidation_error(ctx)
        if not error:
            return None
        ctx.provenance_verified = False
        ctx.append(
            GateResult(
                gate_name="trusted_context_revalidation",
                decision=Decision.DENY,
                risks=[error],
                metadata={
                    "provenance_verified": False,
                    "revalidation": "hitl_resume",
                },
            )
        )
        await self._audit_async(ctx)
        return PipelineResult(
            ctx=ctx,
            allowed=False,
            tool_result=None,
            final_decision=ctx.final_decision,
            final_reason=ctx.final_reason,
        )

    def issue_bound_approval(
        self,
        ctx: GateContext,
        *,
        approver: str,
        reason: str = "",
        ttl_seconds: int = 300,
    ) -> Approval:
        """Issue the only approval form used by runtime control paths."""
        from xa_guard.approval import issue_approval

        return issue_approval(
            trace_id=ctx.trace_id,
            tool_name=ctx.tool_name,
            arguments=ctx.arguments,
            approver=approver,
            reason=reason,
            ttl_seconds=ttl_seconds,
            **self.approval_bindings(ctx),
        )

    def _audit(self, ctx: GateContext) -> GateResult:
        """Write Gate6 evidence and retain its metadata on the shared context."""
        result = self.gate6(ctx, GateStage.OUTBOUND)
        ctx.append(result)
        return result

    async def _audit_async(self, ctx: GateContext) -> GateResult:
        """Use an async Gate6 sink when supplied, preserving file-gate behavior."""
        evaluator = getattr(self.gate6, "evaluate_async", None)
        if evaluator is None:
            result = self.gate6(ctx, GateStage.OUTBOUND)
        else:
            result = await evaluator(ctx, GateStage.OUTBOUND)
        ctx.append(result)
        return result

    def finalize_preflight(self, ctx: GateContext) -> PipelineResult:
        """Audit a domain-specific preflight without re-running generic gates.

        Supply-chain evaluators use this after appending their own GateResult so
        AIBOM's allow/warn/deny semantics are preserved while every operation
        still receives a traceable Gate6 record.
        """
        self._audit(ctx)
        return PipelineResult(
            ctx=ctx,
            allowed=ctx.final_decision not in (Decision.DENY, Decision.REQUIRE_APPROVAL),
            tool_result=None,
            final_decision=ctx.final_decision,
            final_reason=ctx.final_reason,
        )

    async def run(self, ctx: GateContext, executor: ToolExecutor) -> PipelineResult:
        """跑完整 6 关卡 + 工具执行。

        executor: 真正调用下游工具的协程函数（由 proxy.downstream 提供）。
        """
        # Protocol adapters may inject a domain-specific preflight before the
        # generic six-gate flow (for example AIBOM install admission). Preserve
        # the first blocking cause and audit it without evaluating/executing the
        # downstream path again.
        if ctx.final_decision == Decision.DENY:
            await self._audit_async(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        if self.governance is not None and self.governance.enabled:
            result = self.governance.evaluate(ctx)
            ctx.append(result)
            if result.decision in (Decision.DENY, Decision.REQUIRE_APPROVAL):
                await self._audit_async(ctx)
                return PipelineResult(
                    ctx=ctx,
                    allowed=False,
                    tool_result=None,
                    final_decision=ctx.final_decision,
                    final_reason=ctx.final_reason,
                )

        # ---- inbound: input firewall ----
        result = self.gate1(ctx, GateStage.INBOUND)
        _sync_ctx_from_result(ctx, result)
        ctx.append(result)
        if result.decision in (Decision.DENY, Decision.REQUIRE_APPROVAL):
            await self._audit_async(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        # ---- inbound: risk, taint, and policy aggregation ----
        for gate in (self.gate2, self.gate4, self.gate3):
            result = gate(ctx, GateStage.INBOUND)
            _sync_ctx_from_result(ctx, result)
            ctx.append(result)

        if ctx.final_decision in (Decision.DENY, Decision.REQUIRE_APPROVAL):
            # 写一条 audit 后返回；REQUIRE_APPROVAL 同样阻断 executor。
            await self._audit_async(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        # ---- inbound: executor sandbox ----
        result = self.gate5(ctx, GateStage.INBOUND)
        _sync_ctx_from_result(ctx, result)
        ctx.append(result)
        if result.decision in (Decision.DENY, Decision.REQUIRE_APPROVAL):
            await self._audit_async(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        # ---- 工具执行 ----
        tool_result = None
        try:
            tool_result = await executor(ctx)
            ctx.tool_result = tool_result
        except Exception as exc:
            log.exception("downstream tool failed")
            ctx.final_decision = Decision.DENY
            ctx.final_reason = f"tool_error: {type(exc).__name__}: {exc}"
            # 仍写 audit
            await self._audit_async(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=Decision.DENY,
                final_reason=ctx.final_reason,
            )

        # ---- outbound ----
        # 出向先过关卡 4（输出 taint 检查）再过关卡 6（审计）
        out_taint_result = self.gate4(ctx, GateStage.OUTBOUND)
        _sync_ctx_from_result(ctx, out_taint_result)
        ctx.append(out_taint_result)
        if out_taint_result.decision == Decision.DENY:
            ctx.tool_result = None
            tool_result = None

        await self._audit_async(ctx)

        return PipelineResult(
            ctx=ctx,
            allowed=ctx.final_decision != Decision.DENY,
            tool_result=tool_result,
            final_decision=ctx.final_decision,
            final_reason=ctx.final_reason,
        )

    async def run_after_approval(self, ctx: GateContext, executor: ToolExecutor) -> PipelineResult:
        """Resume a REQUIRE_APPROVAL request after an explicit HITL approval.

        The signed request is checked against current identity, provenance, taint,
        policy and effect class.  Governance and Gate1–4 are then re-evaluated
        before the token is atomically consumed and Gate5/executor may run.
        """
        if ctx.final_decision != Decision.REQUIRE_APPROVAL:
            return PipelineResult(
                ctx=ctx,
                allowed=ctx.final_decision != Decision.DENY,
                tool_result=ctx.tool_result,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        from xa_guard.approval import verify_and_consume_approval, verify_approval

        approval = ctx.approval
        bindings = self.approval_bindings(ctx)
        valid, why = verify_approval(
            approval,
            trace_id=ctx.trace_id,
            tool_name=ctx.tool_name,
            arguments=ctx.arguments,
            **bindings,
        )
        if not valid:
            ctx.final_decision = Decision.DENY
            ctx.final_reason = f"approval_token_invalid: {why}"
            await self._audit_async(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        invalid_provenance = await self._deny_invalid_resumed_provenance(ctx)
        if invalid_provenance is not None:
            return invalid_provenance

        # The initial blocked attempt is already immutable in Gate6.  Reset only
        # the in-memory decision accumulator so current controls are evaluated
        # from a clean state while preserving the same trace/request binding.
        ctx.span_id = str(uuid.uuid4())
        ctx.started_at = datetime.now(timezone.utc)
        ctx.risk_level = RiskLevel.GREEN
        ctx.taint = TaintLabel.PUBLIC
        ctx.gate_results = []
        ctx.rule_hits = []
        ctx.final_decision = Decision.ALLOW
        ctx.final_reason = "approval_revalidation_started"
        ctx.tool_result = None
        ctx.tool_result_hash = ""
        ctx.approval = approval

        def append_revalidated(result: GateResult) -> GateResult:
            # A valid token satisfies approval-only outcomes under the exact same
            # bound policy/context.  A DENY is never converted.
            if result.decision == Decision.REQUIRE_APPROVAL:
                result = replace(
                    result,
                    decision=Decision.ALLOW,
                    metadata={
                        **result.metadata,
                        "approval_satisfied": True,
                        "pre_approval_decision": Decision.REQUIRE_APPROVAL.value,
                    },
                    note=(result.note + "; " if result.note else "")
                    + "require_approval satisfied by bound token; controls revalidated",
                )
            _sync_ctx_from_result(ctx, result)
            ctx.append(result)
            return result

        if self.governance is not None and self.governance.enabled:
            result = append_revalidated(self.governance.evaluate(ctx))
            if result.decision == Decision.DENY:
                ctx.final_reason = f"approval_revalidation_denied: {ctx.final_reason}"
                await self._audit_async(ctx)
                return PipelineResult(ctx, False, None, ctx.final_decision, ctx.final_reason)

        result = append_revalidated(self.gate1(ctx, GateStage.INBOUND))
        if result.decision == Decision.DENY:
            ctx.final_reason = f"approval_revalidation_denied: {ctx.final_reason}"
            await self._audit_async(ctx)
            return PipelineResult(ctx, False, None, ctx.final_decision, ctx.final_reason)

        for gate in (self.gate2, self.gate4, self.gate3):
            append_revalidated(gate(ctx, GateStage.INBOUND))
        if ctx.final_decision == Decision.DENY:
            ctx.final_reason = f"approval_revalidation_denied: {ctx.final_reason}"
            await self._audit_async(ctx)
            return PipelineResult(ctx, False, None, ctx.final_decision, ctx.final_reason)

        invalid_provenance = await self._deny_invalid_resumed_provenance(ctx)
        if invalid_provenance is not None:
            return invalid_provenance

        # Recomputed taint/policy must still match the signed values.  Consume
        # only after revalidation succeeds so a policy denial does not burn the
        # token before its denial is durably audited.
        valid, why = verify_and_consume_approval(
            approval,
            trace_id=ctx.trace_id,
            tool_name=ctx.tool_name,
            arguments=ctx.arguments,
            **self.approval_bindings(ctx),
        )
        if not valid:
            ctx.final_decision = Decision.DENY
            ctx.final_reason = f"approval_revalidation_invalid: {why}"
            await self._audit_async(ctx)
            return PipelineResult(ctx, False, None, ctx.final_decision, ctx.final_reason)

        if ctx.final_decision == Decision.ALLOW:
            ctx.final_reason = "hitl_approved_and_revalidated"

        result = self.gate5(ctx, GateStage.INBOUND)
        _sync_ctx_from_result(ctx, result)
        ctx.append(result)
        if result.decision in (Decision.DENY, Decision.REQUIRE_APPROVAL):
            await self._audit_async(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        tool_result = None
        try:
            tool_result = await executor(ctx)
            ctx.tool_result = tool_result
        except Exception as exc:
            log.exception("downstream tool failed after HITL approval")
            ctx.final_decision = Decision.DENY
            ctx.final_reason = f"tool_error: {type(exc).__name__}: {exc}"
            await self._audit_async(ctx)
            return PipelineResult(
                ctx=ctx,
                allowed=False,
                tool_result=None,
                final_decision=Decision.DENY,
                final_reason=ctx.final_reason,
            )

        out_taint_result = self.gate4(ctx, GateStage.OUTBOUND)
        _sync_ctx_from_result(ctx, out_taint_result)
        ctx.append(out_taint_result)
        if out_taint_result.decision == Decision.DENY:
            ctx.tool_result = None
            tool_result = None

        await self._audit_async(ctx)

        return PipelineResult(
            ctx=ctx,
            allowed=ctx.final_decision != Decision.DENY,
            tool_result=tool_result,
            final_decision=ctx.final_decision,
            final_reason=ctx.final_reason,
        )

    async def reject_after_approval(
        self,
        ctx: GateContext,
        *,
        approver: str = "",
        reason: str = "",
    ) -> PipelineResult:
        """Record an explicit HITL rejection after a REQUIRE_APPROVAL decision.

        The initial pipeline run already wrote a `require_approval` audit row.
        This method appends the operator rejection as a second `deny` row so
        audit replay can prove who rejected the request and why.
        """
        if ctx.final_decision != Decision.REQUIRE_APPROVAL:
            return PipelineResult(
                ctx=ctx,
                allowed=ctx.final_decision != Decision.DENY,
                tool_result=ctx.tool_result,
                final_decision=ctx.final_decision,
                final_reason=ctx.final_reason,
            )

        ctx.approval = Approval(
            approver=approver or "mcp-hitl-user",
            reason=reason,
        )
        ctx.tool_result = None
        ctx.final_decision = Decision.DENY
        ctx.final_reason = "hitl_rejected" if not reason else f"hitl_rejected: {reason}"
        await self._audit_async(ctx)
        return PipelineResult(
            ctx=ctx,
            allowed=False,
            tool_result=None,
            final_decision=ctx.final_decision,
            final_reason=ctx.final_reason,
        )
