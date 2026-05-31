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
    # The caller gets the callee as an internal subagent tool.
    a = next(n for n in g.nodes if n.id == "a")
    assert a.tools == {"tool_grants": ["agentfactory.subagent.b"]}


def test_resolve_grants_tools_from_connected_tool_node() -> None:
    g = resolve(
        Graph.model_validate(
            {
                "nodes": [{"id": "a"}, {"id": "toolbox", "kind": "tool"}],
                "edges": [{"source": "a", "target": "toolbox"}],
                "tool_defs": [
                    {
                        "id": "web-search",
                        "node_id": "toolbox",
                        "args": {"query": {"type_key": "text"}},
                    }
                ],
            }
        )
    )
    a = next(n for n in g.nodes if n.id == "a")
    toolbox = next(n for n in g.nodes if n.id == "toolbox")
    assert a.tools is not None
    assert a.tools["tool_grants"] == ["web-search"]
    assert toolbox.model is None
    assert toolbox.io is None


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


def test_resolve_infers_recursion_depth_from_chain() -> None:
    # a -> b -> c: a's longest subagent chain is 2, b's is 1, c's is 0 (-> min 1).
    g = resolve(
        Graph.model_validate(
            {
                "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                "edges": [
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "c"},
                ],
            }
        )
    )
    by_id = {n.id: n for n in g.nodes}
    assert by_id["a"].policy["max_recursion_depth"] == 2
    assert by_id["b"].policy["max_recursion_depth"] == 1
    assert by_id["c"].policy["max_recursion_depth"] == 1
    # a and b each call one subagent -> budget = one default cap; c has none.
    assert by_id["a"].policy["max_tool_calls"] == 3
    assert "max_tool_calls" not in by_id["c"].policy


def test_resolve_sizes_tool_budget_from_caps() -> None:
    # An explicit per-call cap on the a->b edge drives a's global tool budget.
    g = resolve(
        Graph.model_validate(
            {
                "nodes": [
                    {
                        "id": "a",
                        "tools": {"tool_call_caps": {"agentfactory.subagent.b": 5}},
                    },
                    {"id": "b"},
                ],
                "edges": [{"source": "a", "target": "b"}],
            }
        )
    )
    a = next(n for n in g.nodes if n.id == "a")
    assert a.policy["max_tool_calls"] == 5
    assert a.policy["max_steps"] == 8  # max(8, 5 + 1)


def test_resolve_recursion_depth_survives_cycle() -> None:
    # A cycle has no finite longest chain, so depth falls back to the default.
    g = resolve(
        Graph.model_validate(
            {
                "nodes": [{"id": "a"}, {"id": "b"}],
                "edges": [
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "a"},
                ],
            }
        )
    )
    assert g.nodes[0].policy["max_recursion_depth"] == 2


def test_resolve_preserves_explicit_policy() -> None:
    g = resolve(
        Graph.model_validate(
            {"nodes": [{"id": "a", "policy": {"max_recursion_depth": 7}}]}
        )
    )
    assert g.nodes[0].policy == {"max_recursion_depth": 7}


def test_resolve_does_not_mutate_input() -> None:
    original = Graph.model_validate({"nodes": [{"id": "a", "description": "x"}]})
    resolve(original)
    assert original.nodes[0].model is None  # input untouched
