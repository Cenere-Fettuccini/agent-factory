"""Preview a single agent and dry-run a whole graph, using the real framework.

We never reimplement validation here — we build actual Agent objects and let
the framework accept or reject them.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from composer.build import NodeBuildError, node_to_agent
from composer.graph_validation import ValidationResult, validate_graph
from composer.network_tools import registered_network_tools
from composer.resolver import resolve as resolve_graph
from composer.schemas.graph import Graph, GraphNode, ToolDef
from composer.tool_defs import ToolDefError, registered_tools


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


def preview_agent(
    node: GraphNode, tool_defs: Iterable[ToolDef] = (), graph: Graph | None = None
) -> PreviewResult:
    """Build one agent and return its frozen describe-output.

    ``tool_defs`` are any UI-authored tools the node may grant; they are
    registered transiently so grants validate.
    """
    if node.kind == "tool":
        owned = [td.model_dump(mode="json") for td in tool_defs if td.node_id == node.id]
        return PreviewResult(node_id=node.id, ok=True, agent={"tools": owned})

    try:
        if graph is None:
            with registered_tools(tool_defs):
                agent = node_to_agent(node)
        else:
            graph = resolve_graph(graph)
            node = graph.get(node.id) or node
            with registered_tools(graph.tool_defs), registered_network_tools(graph):
                agent = node_to_agent(node)
    except (NodeBuildError, ToolDefError) as exc:
        return PreviewResult(node_id=node.id, ok=False, error=str(exc))
    return PreviewResult(
        node_id=node.id, ok=True, agent=agent.model_dump(mode="json")
    )


def dry_run(graph: Graph) -> DryRunResult:
    """Structurally validate, then instantiate every node in memory."""
    graph = resolve_graph(graph)
    structural = validate_graph(graph)
    nodes: list[DryRunNode] = []
    try:
        with registered_tools(graph.tool_defs), registered_network_tools(graph):
            for node in graph.nodes:
                if node.kind == "tool":
                    nodes.append(DryRunNode(node_id=node.id, ok=True))
                    continue
                try:
                    node_to_agent(node)
                    nodes.append(DryRunNode(node_id=node.id, ok=True))
                except NodeBuildError as exc:
                    nodes.append(
                        DryRunNode(node_id=node.id, ok=False, error=str(exc))
                    )
    except ToolDefError as exc:
        # A bad/colliding tool definition invalidates the whole graph.
        nodes = [DryRunNode(node_id=n.id, ok=False, error=str(exc)) for n in graph.nodes]

    ok = structural.valid and all(n.ok for n in nodes)
    return DryRunResult(ok=ok, structural=structural, nodes=nodes)
