"""Structural validation of a graph, independent of building any agent.

Checks that the wiring is coherent *before* anything is instantiated:
endpoints exist, ids are unique, recursion stays within declared limits.
"""

from __future__ import annotations

from pydantic import BaseModel

from agentfactory.catalog.models import MODELS
from composer.schemas.graph import Graph

DEFAULT_MAX_RECURSION = 2  # mirrors PolicyLayer.max_recursion_depth default


class ValidationIssue(BaseModel):
    """One structural problem, tied to the node or edge that caused it."""

    severity: str  # "error" | "warning"
    code: str
    message: str
    node_id: str | None = None
    edge: tuple[str, str] | None = None


class ValidationResult(BaseModel):
    """The outcome of structural validation."""

    valid: bool
    issues: list[ValidationIssue]


def _max_recursion(graph: Graph, node_id: str) -> int:
    node = graph.get(node_id)
    if node is None or node.policy is None:
        return DEFAULT_MAX_RECURSION
    value = node.policy.get("max_recursion_depth", DEFAULT_MAX_RECURSION)
    return int(value)


def validate_graph(graph: Graph) -> ValidationResult:
    """Run every structural check and collect issues."""
    issues: list[ValidationIssue] = []

    # 1. Unique node ids.
    seen: set[str] = set()
    for node in graph.nodes:
        if node.id in seen:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="duplicate_node",
                    message=f"node id {node.id!r} appears more than once",
                    node_id=node.id,
                )
            )
        seen.add(node.id)

    ids = set(graph.node_ids())
    kinds = {node.id: node.kind for node in graph.nodes}

    for td in graph.tool_defs:
        if td.node_id is None:
            continue
        owner = graph.get(td.node_id)
        if owner is None:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="dangling_tool_owner",
                    message=f"tool {td.id!r} belongs to missing node {td.node_id!r}",
                    node_id=td.node_id,
                )
            )
        elif owner.kind != "tool":
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="tool_owner_not_tool_node",
                    message=f"tool {td.id!r} belongs to non-tool node {td.node_id!r}",
                    node_id=td.node_id,
                )
            )

    # 2. Edge endpoints exist, and calls stay within a tier or cross to the next.
    adjacency: dict[str, list[str]] = {nid: [] for nid in ids}
    for edge in graph.edges:
        for end in (edge.source, edge.target):
            if end not in ids:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="dangling_edge",
                        message=f"edge endpoint {end!r} is not a node in the graph",
                        edge=(edge.source, edge.target),
                    )
                )
        if kinds.get(edge.source) == "tool":
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="tool_node_has_outgoing_call",
                    message=f"tool node {edge.source!r} cannot call other nodes",
                    node_id=edge.source,
                    edge=(edge.source, edge.target),
                )
            )
        if edge.source in adjacency and edge.target in ids:
            adjacency[edge.source].append(edge.target)
            issues.extend(_check_adjacency(graph, edge.source, edge.target))

    # 2b. A subagent call compiles to a tool grant, so an agent that calls others
    # needs a tool-capable model. Only flagged when the caller's model is set
    # explicitly to a catalogued model that can't use tools — an unset model is
    # left to the Resolver, which only picks tool-capable tiers.
    flagged_callers: set[str] = set()
    for edge in graph.edges:
        src = graph.get(edge.source)
        if src is None or src.kind != "agent" or not src.model or src.id in flagged_callers:
            continue
        model_id = src.model.get("model_id")
        if model_id and MODELS.contains(model_id) and not MODELS.get(model_id).supports_tools:
            flagged_callers.add(src.id)
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="caller_model_no_tools",
                    message=(
                        f"agent {edge.source!r} calls {edge.target!r}, but its model "
                        f"{model_id!r} cannot use tools (a subagent call is a tool call)"
                    ),
                    node_id=edge.source,
                    edge=(edge.source, edge.target),
                )
            )

    # 3. Recursion within declared limits (cycle detection with depth check).
    for cycle in _find_cycles(adjacency):
        limit = min(_max_recursion(graph, nid) for nid in cycle)
        severity = "error" if limit < 1 else "warning"
        issues.append(
            ValidationIssue(
                severity=severity,
                code="recursion",
                message=(
                    f"call cycle {' -> '.join([*cycle, cycle[0]])} "
                    f"(min max_recursion_depth = {limit})"
                ),
                node_id=cycle[0],
            )
        )

    valid = not any(i.severity == "error" for i in issues)
    return ValidationResult(valid=valid, issues=issues)


def _check_adjacency(
    graph: Graph, source: str, target: str
) -> list[ValidationIssue]:
    """A call may stay within a tier or cross to the one directly below it.

    Same-tier calls model peer collaboration (e.g. a coordinator delegating to
    its specialists); the only forbidden moves are calling upward or skipping a
    tier downward. Only enforced when both endpoints carry a tier in
    ``graph.layers``; tierless graphs are validated exactly as before.
    """
    src_node = graph.get(source)
    tgt_node = graph.get(target)
    if src_node is None or tgt_node is None:
        return []
    src_i = graph.layer_index(src_node.layer)
    tgt_i = graph.layer_index(tgt_node.layer)
    if src_i is None or tgt_i is None:
        return []
    if tgt_i != src_i and tgt_i != src_i + 1:
        return [
            ValidationIssue(
                severity="error",
                code="non_adjacent_call",
                message=(
                    f"call {source!r} -> {target!r} crosses tiers "
                    f"{src_node.layer!r} -> {tgt_node.layer!r}; a tier may only "
                    "call its own tier or the one directly below it"
                ),
                edge=(source, target),
            )
        ]
    return []


def _find_cycles(adjacency: dict[str, list[str]]) -> list[list[str]]:
    """Return the node lists of simple cycles (deduplicated by member set)."""
    cycles: list[list[str]] = []
    seen_sets: list[frozenset[str]] = []

    def dfs(start: str, current: str, path: list[str]) -> None:
        for nxt in adjacency.get(current, []):
            if nxt == start and len(path) >= 1:
                key = frozenset(path)
                if key not in seen_sets:
                    seen_sets.append(key)
                    cycles.append(list(path))
            elif nxt not in path:
                dfs(start, nxt, [*path, nxt])

    for node in adjacency:
        dfs(node, node, [node])
    return cycles
