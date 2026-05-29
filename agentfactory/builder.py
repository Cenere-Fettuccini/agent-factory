"""A fluent, order-free, last-write-wins builder for Agent."""

from __future__ import annotations

from typing import Any

from agentfactory.agent import Agent
from agentfactory.base import AgentFactoryError, Identity
from agentfactory.layers.errors import ErrorLayer, ErrorPolicy
from agentfactory.layers.io import IOLayer, IOSchema
from agentfactory.layers.model import ModelLayer
from agentfactory.layers.policy import PolicyLayer
from agentfactory.layers.telemetry import TelemetryLayer
from agentfactory.layers.tools import ToolsLayer


class IncompleteAgentError(AgentFactoryError):
    """Raised when build() is called before required layers are set."""


class AgentBuilder:
    """Accumulates layer configuration, then freezes it into an Agent."""

    def __init__(
        self,
        id: str,
        name: str,
        version: str,
        description: str,
        tags: list[str] | None = None,
    ) -> None:
        self._identity = Identity(
            id=id, name=name, version=version, description=description, tags=tags or []
        )
        self._model: ModelLayer | None = None
        self._io: IOLayer | None = None
        self._tools: ToolsLayer = ToolsLayer()
        self._policy: PolicyLayer = PolicyLayer()
        self._errors: ErrorLayer = ErrorLayer()
        self._telemetry: TelemetryLayer = TelemetryLayer()

    def with_model(self, model_id: str, **fields: Any) -> AgentBuilder:
        self._model = ModelLayer(model_id=model_id, **fields)
        return self

    def with_io(
        self, *, input_schema: IOSchema, output_schema: IOSchema
    ) -> AgentBuilder:
        self._io = IOLayer(input_schema=input_schema, output_schema=output_schema)
        return self

    def with_tools(
        self,
        *,
        grants: list[str] | None = None,
        caller_allowlist: list[str] | None = None,
    ) -> AgentBuilder:
        self._tools = ToolsLayer(
            tool_grants=grants or [], caller_allowlist=caller_allowlist or []
        )
        return self

    def with_policy(self, **fields: Any) -> AgentBuilder:
        self._policy = PolicyLayer(**fields)
        return self

    def with_errors(self, *, policies: list[ErrorPolicy]) -> AgentBuilder:
        self._errors = ErrorLayer(policies=policies)
        return self

    def with_telemetry(self, **fields: Any) -> AgentBuilder:
        self._telemetry = TelemetryLayer(**fields)
        return self

    def build(self) -> Agent:
        if self._model is None:
            raise IncompleteAgentError("model layer was never set; call .with_model(...)")
        if self._io is None:
            raise IncompleteAgentError("io layer was never set; call .with_io(...)")
        return Agent(
            identity=self._identity,
            model=self._model,
            io=self._io,
            tools=self._tools,
            policy=self._policy,
            errors=self._errors,
            telemetry=self._telemetry,
        )
