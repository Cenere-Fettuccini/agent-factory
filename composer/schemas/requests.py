"""Request payloads that wrap a graph with endpoint-specific options."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from composer.schemas.graph import Graph


class ExportRequest(BaseModel):
    """An export: the graph to write plus where to write it."""

    model_config = ConfigDict(extra="forbid")

    graph: Graph
    destination: str
    overwrite: bool = False
