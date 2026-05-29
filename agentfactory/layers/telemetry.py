"""Layer 6: telemetry shape — service name, sampling, redaction, sinks."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from agentfactory.catalog.sinks import SINKS


class TelemetryLayer(BaseModel):
    """How and where this agent's spans are shaped (not where they're shipped)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service_name: str = ""
    resource_attrs: dict[str, str] = {}
    redact_keys: list[str] = []
    sample_rate: float = 1.0
    sinks: list[str] = ["console"]

    @field_validator("sample_rate")
    @classmethod
    def _rate_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"sample_rate {value} must be between 0 and 1")
        return value

    @field_validator("sinks")
    @classmethod
    def _sinks_in_catalog(cls, value: list[str]) -> list[str]:
        unknown = [s for s in value if not SINKS.contains(s)]
        if unknown:
            raise ValueError(
                f"sinks {unknown} are not in the sink catalog; known: {SINKS.ids()}"
            )
        return value
