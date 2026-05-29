"""Preview a single agent and dry-run a whole graph, using the real framework.

We never reimplement validation here — we build actual Agent objects and let
the framework accept or reject them.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from composer.build import NodeBuildError, node_to_agent
from composer.graph_validation import ValidationResult, validate_graph
from composer.schemas.graph import Graph, GraphNode


class PreviewResult(BaseModel):
    """The describe-output of one built agent, or the error that stopped it."""

    node_id: str
    ok: bool
    agent: dict[str, Any] | None = None
    error: str | None = None


class DryRunNode(BaseModel):
    node_id: str
    ok: bool
    error: str | None = None


class DryRunResult(BaseModel):
    """Did every agent in the graph instantiate, and was the graph coherent?"""

    ok: bool
    structural: ValidationResult
    nodes: list[DryRunNode]


def preview_agent(node: GraphNode) -> PreviewResult:
    """Build one agent and return its frozen describe-output."""
    try:
        agent = node_to_agent(node)
    except NodeBuildError as exc:
        return PreviewResult(node_id=node.id, ok=False, error=str(exc))
    return PreviewResult(
        node_id=node.id, ok=True, agent=agent.model_dump(mode="json")
    )


def dry_run(graph: Graph) -> DryRunResult:
    """Structurally validate, then instantiate every node in memory."""
    structural = validate_graph(graph)
    nodes: list[DryRunNode] = []
    for node in graph.nodes:
        try:
            node_to_agent(node)
            nodes.append(DryRunNode(node_id=node.id, ok=True))
        except NodeBuildError as exc:
            nodes.append(DryRunNode(node_id=node.id, ok=False, error=str(exc)))

    ok = structural.valid and all(n.ok for n in nodes)
    return DryRunResult(ok=ok, structural=structural, nodes=nodes)
