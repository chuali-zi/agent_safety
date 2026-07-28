"""Real-model causal experiments for Open Agent Range.

This package is deliberately separate from the deterministic Seat/Oracle path.
It measures two different facts without conflating them:

* whether a model emitted a policy-violating native tool call; and
* whether the same immutable call caused harm behind NullSUT or XA-Guard.
"""

from kernel.live_agent.models import (
    AgentToolCall,
    AgentTurn,
    AttackCase,
    ExperimentConfig,
    PromptProfile,
    ToolIntent,
)
from kernel.live_agent.runner import LiveAgentRunner

__all__ = [
    "AgentToolCall",
    "AgentTurn",
    "AttackCase",
    "ExperimentConfig",
    "LiveAgentRunner",
    "PromptProfile",
    "ToolIntent",
]
