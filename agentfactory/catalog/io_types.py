"""Lexicon of named primitive IO types that IOSchema field specs reference."""

from __future__ import annotations

from typing import Any

from pydantic import AnyUrl, BaseModel, ConfigDict

from agentfactory.catalog.registry import Registry


class IOTypeSpec(BaseModel):
    """A named primitive type usable in an IO schema."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: str
    description: str
    python_type: Any


IO_TYPES: Registry[IOTypeSpec] = Registry("io type")


def seed_defaults() -> None:
    if IO_TYPES.ids():
        return
    IO_TYPES.register("text", IOTypeSpec(id="text", description="A string.", python_type=str))
    IO_TYPES.register(
        "json",
        IOTypeSpec(id="json", description="An arbitrary JSON object.", python_type=dict),
    )
    IO_TYPES.register(
        "number",
        IOTypeSpec(id="number", description="A floating point number.", python_type=float),
    )
    IO_TYPES.register(
        "bool", IOTypeSpec(id="bool", description="A boolean.", python_type=bool)
    )
    IO_TYPES.register(
        "image_url",
        IOTypeSpec(id="image_url", description="A URL pointing to an image.", python_type=AnyUrl),
    )
    IO_TYPES.register(
        "enum",
        IOTypeSpec(id="enum", description="A constrained string choice.", python_type=str),
    )
