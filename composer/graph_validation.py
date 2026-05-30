"""Structural validation of a graph, independent of building any agent.

Checks that the wiring is coherent *before* anything is instantiated:
endpoints exist, ids are unique, recursion stays within declared limits.
"""

from __future__ import annotations

from pydantic import BaseModel

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

    # 2. Edge endpoints exist, and calls only cross to the tier directly below.
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
        if edge.source in adjacency and edge.target in ids:
            adjacency[edge.source].append(edge.target)
            issues.extend(_check_adjacency(graph, edge.source, edge.target))

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
    """A call may only cross from a tier to the one directly below it.

    Only enforced when both endpoints carry a tier in ``graph.layers``; tierless
    graphs are validated exactly as before.
    """
    src_node = graph.get(source)
    tgt_node = graph.get(target)
    if src_node is None or tgt_node is None:
        return []
    src_i = graph.layer_index(src_node.layer)
    tgt_i = graph.layer_index(tgt_node.layer)
    if src_i is None or tgt_i is None:
        return []
    if tgt_i != src_i + 1:
        return [
            ValidationIssue(
                severity="error",
                code="non_adjacent_call",
                message=(
                    f"call {source!r} -> {target!r} crosses tiers "
                    f"{src_node.layer!r} -> {tgt_node.layer!r}; a tier may only "
                    "call the tier directly below it"
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
