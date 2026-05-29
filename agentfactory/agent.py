"""The Agent contract: a frozen composition of identity plus six layers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from agentfactory.base import Identity
from agentfactory.catalog.models import MODELS
from agentfactory.layers.errors import ErrorLayer
from agentfactory.layers.io import IOLayer
from agentfactory.layers.model import ModelLayer
from agentfactory.layers.policy import PolicyLayer
from agentfactory.layers.telemetry import TelemetryLayer
from agentfactory.layers.tools import ToolsLayer


class Agent(BaseModel):
    """A frozen, typed, serialisable agent contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: Identity
    model: ModelLayer
    io: IOLayer
    tools: ToolsLayer = ToolsLayer()
    policy: PolicyLayer = PolicyLayer()
    errors: ErrorLayer = ErrorLayer()
    telemetry: TelemetryLayer = TelemetryLayer()

    @model_validator(mode="after")
    def _cross_layer(self) -> Agent:
        spec = MODELS.get(self.model.model_id)

        if self.tools.tool_grants and not spec.supports_tools:
            raise ValueError(
                f"model {self.model.model_id!r} does not support tools, "
                f"but tool_grants are set: {self.tools.tool_grants}"
            )

        if (
            self.policy.max_output_tokens is not None
            and self.policy.max_output_tokens > spec.context_window
        ):
            raise ValueError(
                f"policy.max_output_tokens {self.policy.max_output_tokens} exceeds "
                f"model context window {spec.context_window}"
            )

        if not self.telemetry.service_name:
            updated = self.telemetry.model_copy(
                update={"service_name": self.identity.id}
            )
            object.__setattr__(self, "telemetry", updated)

        return self
