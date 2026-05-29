"""Layer 2: typed input and output schemas built from the IO type lexicon."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, create_model, field_validator

from agentfactory.catalog.io_types import IO_TYPES


class IOFieldSpec(BaseModel):
    """One field in an IO schema, referencing a catalogued IO type."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type_key: str
    required: bool = True
    description: str = ""

    @field_validator("type_key")
    @classmethod
    def _type_key_in_catalog(cls, value: str) -> str:
        if not IO_TYPES.contains(value):
            raise ValueError(
                f"type_key {value!r} is not in the IO type lexicon; "
                f"known: {IO_TYPES.ids()}"
            )
        return value


class IOSchema(BaseModel):
    """A named collection of typed fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    fields: dict[str, IOFieldSpec]

    def to_pydantic_model(self) -> type[BaseModel]:
        """Build a Pydantic model that validates data against this schema."""
        definitions: dict[str, Any] = {}
        for field_name, spec in self.fields.items():
            py_type = IO_TYPES.get(spec.type_key).python_type
            if spec.required:
                definitions[field_name] = (py_type, ...)
            else:
                definitions[field_name] = (py_type | None, None)
        return create_model(self.name, **definitions)


class IOLayer(BaseModel):
    """The input and output contract for an agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_schema: IOSchema
    output_schema: IOSchema
