"""Foundational types: the error base class and the agent Identity block."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class AgentFactoryError(Exception):
    """Base class for every error raised by AgentFactory."""


class Identity(BaseModel):
    """Immutable identity block for an agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    version: str
    description: str
    tags: list[str] = []

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError(
                f"id {value!r} must match {_ID_RE.pattern!r} "
                "(lowercase, start with a letter, alnum/underscore/hyphen)"
            )
        return value
