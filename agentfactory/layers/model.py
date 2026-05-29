"""Layer 1: model selection and sampling parameters."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from agentfactory.catalog.models import MODELS


class ModelLayer(BaseModel):
    """Which catalogued model to call, and how."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    temperature: float = 0.7
    max_output_tokens: int | None = None
    system_prompt: str | None = None

    @field_validator("model_id")
    @classmethod
    def _model_id_in_catalog(cls, value: str) -> str:
        if not MODELS.contains(value):
            raise ValueError(
                f"model_id {value!r} is not in the model catalog; "
                f"known: {MODELS.ids()}"
            )
        return value

    @field_validator("temperature")
    @classmethod
    def _temperature_range(cls, value: float) -> float:
        if not 0.0 <= value <= 2.0:
            raise ValueError(f"temperature {value} must be between 0 and 2")
        return value

    @field_validator("max_output_tokens")
    @classmethod
    def _positive_tokens(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError(f"max_output_tokens {value} must be >= 1")
        return value
