"""Runtime layer — executor, sink implementations, and supporting protocols.

The contract chain in :mod:`agentfactory.core` declares *what* an agent is.
This package provides the *how*: a synchronous executor that walks the contract,
enforces runtime ceilings, dispatches model and tool calls through injected
clients, and fans events out to configured sinks.
"""

from agentfactory.runtime.executor import (
    AgentExecutor,
    BudgetExceeded,
    ExecutionError,
    ModelCallResult,
    ModelClient,
    PolicyViolation,
    ToolCallResult,
    ToolDispatcher,
)
from agentfactory.runtime.sinks import (
    FileSinkImpl,
    LangfuseSinkImpl,
    NullSinkImpl,
    Sink,
    StdoutSinkImpl,
    create_sink,
)

__all__ = [
    "AgentExecutor",
    "ExecutionError",
    "BudgetExceeded",
    "PolicyViolation",
    "ModelClient",
    "ToolDispatcher",
    "ModelCallResult",
    "ToolCallResult",
    "Sink",
    "NullSinkImpl",
    "StdoutSinkImpl",
    "FileSinkImpl",
    "LangfuseSinkImpl",
    "create_sink",
]
