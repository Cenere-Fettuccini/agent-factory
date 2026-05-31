"""Authoring endpoints: validate, resolve, preview, dry-run, export."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from composer.export import ExportError, ExportResult, export_graph
from composer.graph_validation import ValidationResult, validate_graph
from composer.preview import (
    DryRunResult,
    PreviewResult,
    dry_run,
    preview_agent,
)
from composer.resolver import resolve
from composer.schemas.graph import Graph, ToolDef
from composer.schemas.requests import ExportRequest, PreviewRequest
from composer.tool_defs import validate_tool_def

router = APIRouter(tags=["authoring"])


@router.post("/graph/validate")
def post_graph_validate(graph: Graph) -> ValidationResult:
    """Structurally validate a graph (no agents instantiated)."""
    return validate_graph(graph)


@router.post("/presets/resolve")
def post_presets_resolve(graph: Graph) -> Graph:
    """Fill unset fields and propagate edge wiring. Returns a new graph."""
    return resolve(graph)


@router.post("/agents/preview")
def post_agents_preview(request: PreviewRequest) -> PreviewResult:
    """Build one agent and return its frozen describe-output."""
    return preview_agent(request.node, request.tool_defs, request.graph)


@router.post("/tools/validate")
def post_tools_validate(tool_def: ToolDef) -> dict[str, Any]:
    """Validate one UI-authored tool and echo its derived JSON Schema."""
    return validate_tool_def(tool_def)


@router.post("/export/dry-run")
def post_export_dry_run(graph: Graph) -> DryRunResult:
    """Validate and instantiate every agent in memory, writing nothing."""
    return dry_run(graph)


@router.post("/export")
def post_export(request: ExportRequest) -> ExportResult:
    """Write the graph to a folder. Refuses dangerous destinations."""
    try:
        return export_graph(
            request.graph, request.destination, overwrite=request.overwrite
        )
    except ExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
