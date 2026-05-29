"""Layer 5: per-error-class handling policies."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from agentfactory.catalog.errors import ERRORS, ErrorAction, ErrorClassSpec


class ErrorPolicy(BaseModel):
    """How to handle one catalogued error class."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    on: str
    action: ErrorAction
    max_retries: int = 0

    @field_validator("on")
    @classmethod
    def _on_in_catalog(cls, value: str) -> str:
        if not ERRORS.contains(value):
            raise ValueError(
                f"error class {value!r} is not in the error catalog; "
                f"known: {ERRORS.ids()}"
            )
        return value

    @field_validator("max_retries")
    @classmethod
    def _non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError(f"max_retries {value} must be >= 0")
        return value


class ErrorLayer(BaseModel):
    """The set of error-handling policies for an agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policies: list[ErrorPolicy] = []

    def action_for(self, error_id: str) -> ErrorPolicy:
        """Resolve the policy for an error id, falling back to the catalog default."""
        for policy in self.policies:
            if policy.on == error_id:
                return policy
        spec: ErrorClassSpec = ERRORS.get(error_id)
        return ErrorPolicy(on=spec.id, action=spec.default_action, max_retries=0)
