"""Layer 4: the policy envelope — limits enforced around the model call."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class PolicyLayer(BaseModel):
    """Runtime limits enforced by the executor, not the model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_steps: int = 8
    max_tool_calls: int = 16
    max_recursion_depth: int = 2
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    timeout_seconds: float = 60.0

    @field_validator("max_steps", "max_tool_calls", "max_recursion_depth")
    @classmethod
    def _at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError(f"value {value} must be >= 1")
        return value

    @field_validator("max_input_tokens", "max_output_tokens")
    @classmethod
    def _positive_optional(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError(f"value {value} must be >= 1")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"timeout_seconds {value} must be > 0")
        return value
