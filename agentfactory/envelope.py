"""Input/output envelopes carrying data, metadata, and trace correlation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from agentfactory.base import AgentFactoryError
from agentfactory.layers.io import IOSchema


class EnvelopeValidationError(AgentFactoryError):
    """Raised when envelope data does not satisfy an IO schema."""


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    trace_id: str | None = None
    parent_span_id: str | None = None

    def validate_against(self, schema: IOSchema) -> dict[str, Any]:
        """Validate ``data`` against ``schema``; return the coerced dict."""
        model = schema.to_pydantic_model()
        try:
            validated = model(**self.data)
        except ValidationError as exc:
            raise EnvelopeValidationError(
                f"envelope data failed schema {schema.name!r}: {exc}"
            ) from exc
        return validated.model_dump()


class InputEnvelope(_Envelope):
    """An inbound request to an agent."""


class OutputEnvelope(_Envelope):
    """An agent's validated response."""
