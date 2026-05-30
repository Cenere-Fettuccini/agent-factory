"""Tests for structural graph validation."""

from __future__ import annotations

from composer.graph_validation import validate_graph
from composer.schemas.graph import Graph


def _g(data: dict) -> Graph:
    return Graph.model_validate(data)


def test_empty_graph_is_valid() -> None:
    assert validate_graph(_g({"nodes": [], "edges": []})).valid


def test_duplicate_node_id() -> None:
    result = validate_graph(_g({"nodes": [{"id": "a"}, {"id": "a"}]}))
    assert not result.valid
    assert any(i.code == "duplicate_node" for i in result.issues)


def test_dangling_edge() -> None:
    result = validate_graph(
        _g({"nodes": [{"id": "a"}], "edges": [{"source": "a", "target": "ghost"}]})
    )
    assert not result.valid
    issue = next(i for i in result.issues if i.code == "dangling_edge")
    assert issue.edge == ("a", "ghost")


def test_cycle_within_limit_is_warning() -> None:
    # default max_recursion_depth = 2 >= 1, so a cycle is a warning, not an error
    result = validate_graph(
        _g(
            {
                "nodes": [{"id": "a"}, {"id": "b"}],
                "edges": [
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "a"},
                ],
            }
        )
    )
    assert result.valid  # warnings don't invalidate
    assert any(i.code == "recursion" and i.severity == "warning" for i in result.issues)


def test_adjacent_tier_call_is_valid() -> None:
    result = validate_graph(
        _g(
            {
                "layers": ["refine", "orchestrate", "tools"],
                "nodes": [
                    {"id": "r", "layer": "refine"},
                    {"id": "o", "layer": "orchestrate"},
                ],
                "edges": [{"source": "r", "target": "o"}],
            }
        )
    )
    assert result.valid
    assert not any(i.code == "non_adjacent_call" for i in result.issues)


def test_non_adjacent_tier_call_is_error() -> None:
    result = validate_graph(
        _g(
            {
                "layers": ["refine", "orchestrate", "tools"],
                "nodes": [
                    {"id": "r", "layer": "refine"},
                    {"id": "t", "layer": "tools"},
                ],
                "edges": [{"source": "r", "target": "t"}],  # skips a tier
            }
        )
    )
    assert not result.valid
    issue = next(i for i in result.issues if i.code == "non_adjacent_call")
    assert issue.edge == ("r", "t")


def test_upward_call_is_error() -> None:
    result = validate_graph(
        _g(
            {
                "layers": ["refine", "orchestrate"],
                "nodes": [
                    {"id": "r", "layer": "refine"},
                    {"id": "o", "layer": "orchestrate"},
                ],
                "edges": [{"source": "o", "target": "r"}],  # calls upward
            }
        )
    )
    assert any(i.code == "non_adjacent_call" for i in result.issues)


def test_tierless_graph_skips_adjacency_check() -> None:
    # No layers declared -> adjacency is not enforced (back-compat).
    result = validate_graph(
        _g({"nodes": [{"id": "a"}, {"id": "b"}], "edges": [{"source": "a", "target": "b"}]})
    )
    assert not any(i.code == "non_adjacent_call" for i in result.issues)


def test_cycle_exceeding_limit_is_error() -> None:
    result = validate_graph(
        _g(
            {
                "nodes": [
                    {"id": "a", "policy": {"max_recursion_depth": 0}},
                    {"id": "b"},
                ],
                "edges": [
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "a"},
                ],
            }
        )
    )
    assert not result.valid
    assert any(i.code == "recursion" and i.severity == "error" for i in result.issues)
