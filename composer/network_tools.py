"""Internal subagent tools derived from graph edges.

When an exported graph says ``A -> B``, the source agent needs a catalogued tool
grant before its contract can be loaded. These helpers materialise those
edge-derived tools transiently for preview/dry-run/export validation; export
also writes a runtime module with real implementations.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel

from agentfactory.catalog.tools import TOOLS, ToolSpec
from agentfactory.layers.io import IOLayer
from composer.resolver import subagent_tool_id
from composer.schemas.graph import Graph, GraphNode
from composer.tool_defs import ToolDefError


class NetworkToolError(Exception):
    """Raised when graph-derived subagent tools cannot be materialised."""


def agent_edge_targets(graph: Graph) -> list[GraphNode]:
    """Return unique agent nodes targeted by call edges."""
    out: list[GraphNode] = []
    seen: set[str] = set()
    for edge in graph.edges:
        target = graph.get(edge.target)
        if target is None or target.kind != "agent" or target.id in seen:
            continue
        seen.add(target.id)
        out.append(target)
    return out


def _io_for(node: GraphNode) -> IOLayer:
    if node.io is None:
        raise NetworkToolError(
            f"subagent target {node.id!r} has no io layer; resolve or set it first"
        )
    return IOLayer.model_validate(node.io)


def _callable_for(agent_id: str, input_model: type[BaseModel]) -> Callable[..., Any]:
    def _impl(**kwargs: Any) -> Any:
        raise NotImplementedError(
            f"subagent tool for {agent_id!r} is validation-only in this process"
        )

    _impl.__name__ = f"call_{agent_id.replace('-', '_')}"
    parameters = [
        inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for name in input_model.model_fields
    ]
    _impl.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
    return _impl


def node_to_subagent_spec(node: GraphNode) -> ToolSpec:
    """Build a catalog ToolSpec for calling ``node`` as an internal subagent."""
    io = _io_for(node)
    input_model = io.input_schema.to_pydantic_model()
    return ToolSpec(
        id=subagent_tool_id(node.id),
        description=f"Call internal agent {node.id}.",
        arg_schema=input_model,
        return_schema=io.output_schema.to_pydantic_model(),
        callable=_callable_for(node.id, input_model),
    )


@contextmanager
def registered_network_tools(graph: Graph) -> Iterator[None]:
    """Register edge-derived subagent tools for the duration of a validation."""
    added: list[str] = []
    try:
        for node in agent_edge_targets(graph):
            spec = node_to_subagent_spec(node)
            if TOOLS.contains(spec.id):
                continue
            TOOLS.register(spec.id, spec)
            added.append(spec.id)
        yield
    except NetworkToolError as exc:
        raise ToolDefError(str(exc)) from exc
    finally:
        for tool_id in added:
            if TOOLS.contains(tool_id):
                TOOLS.unregister(tool_id)
