"""Catalog of callable tools an agent may be granted."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from agentfactory.catalog.registry import Registry


class ToolSpec(BaseModel):
    """A registered tool: its schema and the callable that implements it."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: str
    description: str
    arg_schema: type[BaseModel]
    return_schema: type[BaseModel] | None = None
    callable: Callable[..., Any]


TOOLS: Registry[ToolSpec] = Registry("tool")


def seed_defaults() -> None:
    """No default tools. Tests and host apps register their own."""
