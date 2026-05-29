"""Catalog of standardized error classes and their default handling."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentfactory.catalog.registry import Registry

ErrorAction = Literal["raise", "retry", "log"]


class ErrorClassSpec(BaseModel):
    """A catalogued error class with a default handling action."""

    model_config = ConfigDict(frozen=True)

    id: str
    description: str
    default_action: ErrorAction


ERRORS: Registry[ErrorClassSpec] = Registry("error class")


def seed_defaults() -> None:
    if ERRORS.ids():
        return
    ERRORS.register(
        "tool_failure",
        ErrorClassSpec(
            id="tool_failure", description="A tool raised an exception.", default_action="retry"
        ),
    )
    ERRORS.register(
        "model_timeout",
        ErrorClassSpec(
            id="model_timeout", description="The model call timed out.", default_action="retry"
        ),
    )
    ERRORS.register(
        "policy_exceeded",
        ErrorClassSpec(
            id="policy_exceeded",
            description="A policy limit was exceeded.",
            default_action="raise",
        ),
    )
    ERRORS.register(
        "validation_failure",
        ErrorClassSpec(
            id="validation_failure",
            description="Input or output failed schema validation.",
            default_action="raise",
        ),
    )
    ERRORS.register(
        "unknown",
        ErrorClassSpec(
            id="unknown", description="An unclassified error.", default_action="raise"
        ),
    )
