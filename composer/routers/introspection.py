"""Introspection endpoints: the framework's live shape."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from composer.introspection import catalog_payload, node_type_schemas

router = APIRouter(tags=["introspection"])


@router.get("/node-types")
def get_node_types() -> dict[str, Any]:
    """JSON Schema for every layer, derived live from the Pydantic classes."""
    return node_type_schemas()


@router.get("/catalogs")
def get_catalogs() -> dict[str, Any]:
    """Every catalog (models, io_types, tools, errors, sinks) as JSON."""
    return catalog_payload()
