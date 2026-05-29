"""Tests for preview and dry-run (real-framework instantiation)."""

from __future__ import annotations

from composer.preview import dry_run, preview_agent
from composer.resolver import resolve
from composer.schemas.graph import Graph, GraphNode


def _resolved_node(**data: object) -> GraphNode:
    return resolve(Graph(nodes=[GraphNode.model_validate(data)])).nodes[0]


def test_preview_builds_describe_output() -> None:
    node = _resolved_node(id="prev", description="summarise text")
    result = preview_agent(node)
    assert result.ok
    assert result.agent is not None
    assert result.agent["identity"]["id"] == "prev"
    assert result.agent["model"]["model_id"] == "anthropic:claude-sonnet-4-6"


def test_preview_unbuildable_node_reports_error() -> None:
    # No model and no io, and not resolved -> NodeBuildError surfaced as ok=False.
    result = preview_agent(GraphNode(id="bad"))
    assert not result.ok
    assert result.error is not None


def test_preview_surfaces_framework_validation_error() -> None:
    node = GraphNode.model_validate(
        {
            "id": "bad-model",
            "model": {"model_id": "nope:nope"},
            "io": {
                "input_schema": {"name": "I", "fields": {"q": {"type_key": "text"}}},
                "output_schema": {"name": "O", "fields": {"a": {"type_key": "text"}}},
            },
        }
    )
    result = preview_agent(node)
    assert not result.ok
    assert "model catalog" in (result.error or "")


def test_dry_run_whole_graph() -> None:
    g = resolve(
        Graph.model_validate(
            {
                "nodes": [
                    {"id": "a", "description": "plan"},
                    {"id": "b", "description": "classify"},
                ],
                "edges": [{"source": "a", "target": "b"}],
            }
        )
    )
    result = dry_run(g)
    assert result.ok
    assert all(n.ok for n in result.nodes)
    assert result.structural.valid
