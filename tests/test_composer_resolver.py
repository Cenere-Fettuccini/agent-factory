"""Tests for the deterministic Resolver."""

from __future__ import annotations

from composer.resolver import infer_model_for_layer, infer_model_id, resolve
from composer.schemas.graph import Graph


def test_tier_inference() -> None:
    assert infer_model_id("Plan and reason about a complex problem") == (
        "anthropic:claude-opus-4-7"
    )
    assert infer_model_id("Quickly classify and route the request") == (
        "anthropic:claude-haiku-4-5"
    )
    assert infer_model_id("Write a friendly reply") == (
        "anthropic:claude-sonnet-4-6"
    )


def test_resolve_fills_unset_model_and_io() -> None:
    g = resolve(Graph.model_validate({"nodes": [{"id": "a", "description": "do a thing"}]}))
    node = g.nodes[0]
    assert node.model == {"model_id": "anthropic:claude-sonnet-4-6"}
    assert node.io is not None
    assert "input_schema" in node.io


def test_resolve_preserves_explicit_choices() -> None:
    g = resolve(
        Graph.model_validate(
            {
                "nodes": [
                    {
                        "id": "a",
                        "description": "reason deeply",  # would imply opus
                        "model": {"model_id": "test:echo"},  # but explicit wins
                    }
                ]
            }
        )
    )
    assert g.nodes[0].model == {"model_id": "test:echo"}


def test_resolve_propagates_caller_allowlist() -> None:
    g = resolve(
        Graph.model_validate(
            {
                "nodes": [{"id": "a"}, {"id": "b"}],
                "edges": [{"source": "a", "target": "b"}],
            }
        )
    )
    b = next(n for n in g.nodes if n.id == "b")
    assert b.tools is not None
    assert b.tools["caller_allowlist"] == ["a"]
    # The caller itself gets no inbound edges, so no allowlist is forced.
    a = next(n for n in g.nodes if n.id == "a")
    assert a.tools is None


def test_layer_biases_model() -> None:
    assert infer_model_for_layer("Tools") == "anthropic:claude-haiku-4-5"
    assert infer_model_for_layer("Orchestrator") == "anthropic:claude-opus-4-7"
    assert infer_model_for_layer("Refinement") == "anthropic:claude-opus-4-7"
    assert infer_model_for_layer("whatever") is None
    assert infer_model_for_layer(None) is None


def test_resolve_uses_layer_for_unset_model() -> None:
    # A tool-tier node with a neutral description still resolves to the fast tier.
    g = resolve(
        Graph.model_validate(
            {
                "layers": ["tools"],
                "nodes": [{"id": "t", "layer": "tools", "description": "do a thing"}],
            }
        )
    )
    assert g.nodes[0].model == {"model_id": "anthropic:claude-haiku-4-5"}


def test_explicit_model_still_wins_over_layer() -> None:
    g = resolve(
        Graph.model_validate(
            {
                "layers": ["tools"],
                "nodes": [
                    {"id": "t", "layer": "tools", "model": {"model_id": "test:echo"}}
                ],
            }
        )
    )
    assert g.nodes[0].model == {"model_id": "test:echo"}


def test_resolve_does_not_mutate_input() -> None:
    original = Graph.model_validate({"nodes": [{"id": "a", "description": "x"}]})
    resolve(original)
    assert original.nodes[0].model is None  # input untouched
