"""AgentFactory — a typed, layered framework for building well-bounded agents."""

from agentfactory.core.base import BaseAgent
from agentfactory.core.layers import (
    ErrorLayer,
    IOLayer,
    LogLayer,
    ModelLayer,
    PolicyLayer,
    ToolLayer,
)

# The fully-composed concrete agent type. Convention: when users want "an
# agent", they import this — it sits at the bottom of the inheritance chain
# and carries every dimension of the contract.
Agent = LogLayer

__all__ = [
    "BaseAgent",
    "ModelLayer",
    "IOLayer",
    "ToolLayer",
    "PolicyLayer",
    "ErrorLayer",
    "LogLayer",
    "Agent",
    "AgentBuilder",
]


def __getattr__(name: str):
    # Lazy import to avoid circular dependency: builder imports Agent (this
    # module's alias for LogLayer), which is defined above.
    if name == "AgentBuilder":
        from agentfactory.builder import AgentBuilder
        return AgentBuilder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
__version__ = "0.0.1"
