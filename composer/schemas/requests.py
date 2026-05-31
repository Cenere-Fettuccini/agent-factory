"""Request payloads that wrap a graph with endpoint-specific options."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from composer.schemas.graph import Graph, GraphNode, ToolDef


class ExportRequest(BaseModel):
    """An export: the graph to write plus where to write it."""

    model_config = ConfigDict(extra="forbid")

    graph: Graph
    destination: str
    overwrite: bool = False


class PreviewRequest(BaseModel):
    """Preview one node, with any UI-authored tools it may grant."""

    model_config = ConfigDict(extra="forbid")

    node: GraphNode
    tool_defs: list[ToolDef] = Field(default_factory=list)
    graph: Graph | None = None
