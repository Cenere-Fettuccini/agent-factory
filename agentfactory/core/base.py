"""Layer 1 — BaseAgent.

The universal ancestor for every agent in the system. Carries identity only —
no model, no IO, no tools, no policy. Its single job is to make
``isinstance(x, BaseAgent)`` a meaningful, framework-wide invariant so that
registries, dispatchers, audit logs, and type guards have something to anchor on.

Higher layers (ModelLayer, IOLayer, ...) inherit from BaseAgent and add
behavioral dimensions. BaseAgent itself contributes no behavior.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Semver-ish: MAJOR.MINOR.PATCH with optional pre-release suffix.
_VERSION_PATTERN = r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$"

# Lowercase kebab-case identifier, 1-64 chars. Forces a flat, predictable
# namespace for agent IDs across registries.
_ID_PATTERN = r"^[a-z][a-z0-9-]{0,63}$"


class BaseAgent(BaseModel):
    """Identity anchor for all agents.

    All higher layers extend this. Instances are immutable; build a new one
    rather than mutating fields.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    id: str = Field(
        ...,
        pattern=_ID_PATTERN,
        description="Stable, unique identifier. Kebab-case, used as registry key.",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Human-readable name.",
    )
    version: str = Field(
        ...,
        pattern=_VERSION_PATTERN,
        description="Semantic version of this agent definition.",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="One-paragraph summary of what this agent does.",
    )
    tags: frozenset[str] = Field(
        default_factory=frozenset,
        description="Free-form tags for discovery and grouping.",
    )

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, v: object) -> frozenset[str]:
        if v is None:
            return frozenset()
        if isinstance(v, (list, tuple, set, frozenset)):
            return frozenset(str(t) for t in v)
        raise TypeError("tags must be an iterable of strings")

    def describe(self) -> str:
        """One-line human summary. Useful for logs and registry listings."""
        return f"{self.id}@{self.version} — {self.name}"

    def with_tags(self, *tags: str) -> Self:
        """Return a copy with additional tags. Immutability-friendly update."""
        return self.model_copy(update={"tags": self.tags | frozenset(tags)})
