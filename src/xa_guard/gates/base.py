"""Gate 抽象基类。所有关卡子类化此 + 实现 evaluate()。"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum

from xa_guard.config import GateConfig
from xa_guard.types import Decision, GateContext, GateResult


class GateStage(str, Enum):
    """关卡执行阶段。Gate4 / Gate6 需要进出向各跑一次。"""

    INBOUND = "inbound"     # 工具调用前
    OUTBOUND = "outbound"   # 工具返回后


class Gate(ABC):
    """所有关卡的统一接口。

    子类应：
    1. 实现 `evaluate(ctx, stage)` 返回 GateResult。
    2. 默认实现 latency_ms 自动计时。
    3. 不要在 evaluate 中 mutate ctx — 由 pipeline 统一 append。
    """

    name: str = "gate"
    supported_stages: tuple[GateStage, ...] = (GateStage.INBOUND,)
    fail_closed_on_error = False

    def __init__(self, cfg: GateConfig | None = None) -> None:
        self.cfg = cfg or GateConfig()

    @property
    def enabled(self) -> bool:
        return self.cfg.enabled

    def opt(self, key: str, default=None):
        return self.cfg.options.get(key, default)

    @abstractmethod
    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        """实施关卡检查；返回 GateResult。"""

    @staticmethod
    def effect_class(ctx: GateContext) -> str:
        """Return an explicit conservative effect class for error handling.

        The mapping makes legacy contexts safe without forcing every existing
        caller to populate a new field. New adapters should set effect_class
        directly to read_only/local_write/external_write/privileged_execute.
        """
        explicit = str(getattr(ctx, "effect_class", "") or "").lower()
        if explicit in {"read_only", "local_write", "external_write", "privileged_execute"}:
            return explicit
        level = str(getattr(ctx, "side_effect_level", "") or "").lower()
        # ``none`` is GateContext's historical default, not evidence that a
        # tool is read-only. Only an explicit trusted effect_class can claim
        # that. Named contract levels are safe to honour below.
        if level in {"read", "readonly", "read_only"}:
            return "read_only"
        if level in {"external", "external_write", "network", "network_external"}:
            return "external_write"
        if level in {"privileged", "privileged_execute", "high", "critical"}:
            return "privileged_execute"
        tool = str(getattr(ctx, "tool_name", "") or "").lower()
        if tool.startswith(("get_", "list_", "read_", "search_", "verify_", "describe_", "query_")):
            return "read_only"
        if tool.startswith(("send_", "post_", "publish_", "notify_", "export_", "upload_", "webhook_")):
            return "external_write"
        if tool.startswith(("exec_", "install_", "delete_", "restart_", "deploy_", "grant_", "revoke_")):
            return "privileged_execute"
        # Unknown tool effects must never receive a WARN-and-continue path.
        return "local_write"

    def error_result(self, ctx: GateContext, exc: Exception, latency_ms: float) -> GateResult:
        """Reusable Gate1–5 degradation matrix; never silently continues writes."""
        effect = self.effect_class(ctx)
        configured = self.opt(f"error_decision_{effect}")
        defaults = {
            "read_only": Decision.WARN,
            "local_write": Decision.REQUIRE_APPROVAL,
            "external_write": Decision.DENY,
            "privileged_execute": Decision.DENY,
        }
        try:
            decision = Decision(str(configured)) if configured is not None else defaults[effect]
        except ValueError:
            decision = defaults[effect]
        safe_choices = {
            "read_only": {
                Decision.WARN,
                Decision.REQUIRE_APPROVAL,
                Decision.DENY,
            },
            "local_write": {Decision.REQUIRE_APPROVAL, Decision.DENY},
            "external_write": {Decision.DENY},
            "privileged_execute": {Decision.DENY},
        }
        if decision not in safe_choices[effect]:
            decision = defaults[effect]
        return GateResult(
            gate_name=self.name,
            decision=decision,
            risks=[f"gate_error: {type(exc).__name__}: {exc}"],
            metadata={"degraded": True, "error_policy": effect, "effect_class": effect},
            latency_ms=latency_ms,
            note="gate evaluation degraded under explicit safety policy",
        )

    def __call__(self, ctx: GateContext, stage: GateStage = GateStage.INBOUND) -> GateResult:
        if not self.enabled:
            return GateResult(gate_name=self.name, decision=Decision.ALLOW, note="disabled")
        if stage not in self.supported_stages:
            return GateResult(gate_name=self.name, decision=Decision.ALLOW, note=f"stage {stage} skipped")
        t0 = time.perf_counter()
        try:
            result = self.evaluate(ctx, stage)
        except Exception as exc:  # 关卡内部异常不应崩 pipeline
            if self.fail_closed_on_error:
                raise
            return self.error_result(ctx, exc, (time.perf_counter() - t0) * 1000)
        result.latency_ms = (time.perf_counter() - t0) * 1000
        if not result.gate_name:
            result.gate_name = self.name
        return result
