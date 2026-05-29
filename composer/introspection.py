"""Derive the framework's shape at runtime: node-type schemas and catalogs.

The backend's truth is whatever the framework imports right now. A framework
upgrade automatically updates what every client sees — nothing is hand-mirrored.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from agentfactory.base import Identity
from agentfactory.catalog.errors import ERRORS
from agentfactory.catalog.io_types import IO_TYPES
from agentfactory.catalog.models import MODELS
from agentfactory.catalog.sinks import SINKS
from agentfactory.catalog.tools import TOOLS
from agentfactory.layers.errors import ErrorLayer
from agentfactory.layers.io import IOLayer
from agentfactory.layers.model import ModelLayer
from agentfactory.layers.policy import PolicyLayer
from agentfactory.layers.telemetry import TelemetryLayer
from agentfactory.layers.tools import ToolsLayer

# The six layers plus identity, keyed by the name clients use.
_LAYER_TYPES: dict[str, type[BaseModel]] = {
    "identity": Identity,
    "model": ModelLayer,
    "io": IOLayer,
    "tools": ToolsLayer,
    "policy": PolicyLayer,
    "errors": ErrorLayer,
    "telemetry": TelemetryLayer,
}


def node_type_schemas() -> dict[str, Any]:
    """JSON Schema for every layer, derived directly from the Pydantic classes."""
    return {
        name: model.model_json_schema() for name, model in _LAYER_TYPES.items()
    }


def catalog_payload() -> dict[str, Any]:
    """Every catalog serialized to JSON-safe structures."""
    return {
        "models": [MODELS.get(i).model_dump() for i in MODELS.ids()],
        "io_types": [_io_type(i) for i in IO_TYPES.ids()],
        "tools": [_tool(i) for i in TOOLS.ids()],
        "errors": [ERRORS.get(i).model_dump() for i in ERRORS.ids()],
        "sinks": [SINKS.get(i).model_dump() for i in SINKS.ids()],
    }


def _io_type(type_id: str) -> dict[str, Any]:
    spec = IO_TYPES.get(type_id)
    py = spec.python_type
    return {
        "id": spec.id,
        "description": spec.description,
        "python_type": getattr(py, "__name__", str(py)),
    }


def _tool(tool_id: str) -> dict[str, Any]:
    spec = TOOLS.get(tool_id)
    return {
        "id": spec.id,
        "description": spec.description,
        "arg_schema": spec.arg_schema.model_json_schema(),
        "return_schema": (
            spec.return_schema.model_json_schema()
            if spec.return_schema is not None
            else None
        ),
    }
