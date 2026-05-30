"""Fill unset node fields from descriptions, and propagate wiring across edges.

Deterministic: the same graph in always yields the same graph out, with no
network call. Only *unset* fields are touched — anything the author chose
explicitly is preserved. Edge-derived wiring (caller allowlists) is unioned in.
"""

from __future__ import annotations

from agentfactory.catalog.models import MODELS
from composer.schemas.graph import Graph, GraphNode

# Model-tier catalog ids. Falls back gracefully if a tier isn't catalogued.
_TIER_OPUS = "anthropic:claude-opus-4-7"
_TIER_SONNET = "anthropic:claude-sonnet-4-6"
_TIER_HAIKU = "anthropic:claude-haiku-4-5"

# Description keywords that bump a node up or down a tier.
_OPUS_WORDS = frozenset(
    {
        "reason", "reasoning", "complex", "plan", "planning", "analyze",
        "analysis", "research", "architect", "strategy", "synthesize", "design",
    }
)
_HAIKU_WORDS = frozenset(
    {
        "classify", "classification", "route", "routing", "fast", "simple",
        "extract", "extraction", "tag", "filter", "lookup", "quick", "detect",
    }
)


def infer_model_id(description: str) -> str:
    """Pick a model tier from a one-line description. Defaults to the mid tier."""
    words = {w.strip(".,;:!?()").lower() for w in description.split()}
    if words & _OPUS_WORDS:
        tier = _TIER_OPUS
    elif words & _HAIKU_WORDS:
        tier = _TIER_HAIKU
    else:
        tier = _TIER_SONNET
    # Stay honest about the catalog: never resolve to something that isn't there.
    return tier if MODELS.contains(tier) else _TIER_SONNET


def infer_model_for_layer(layer: str | None) -> str | None:
    """Bias a model tier from the node's network role, if the name is telling.

    Tool tiers want a fast model; orchestration/refinement tiers want reasoning.
    Returns None when the layer name carries no signal, so the caller can fall
    back to description-based inference.
    """
    if not layer:
        return None
    name = layer.lower()
    if "tool" in name:
        tier = _TIER_HAIKU
    elif any(k in name for k in ("orchestr", "plan", "reason", "refine")):
        tier = _TIER_OPUS
    else:
        return None
    return tier if MODELS.contains(tier) else _TIER_SONNET


def _starter_io() -> dict[str, object]:
    return {
        "input_schema": {
            "name": "Input",
            "fields": {"input": {"type_key": "text"}},
        },
        "output_schema": {
            "name": "Output",
            "fields": {"output": {"type_key": "text"}},
        },
    }


def resolve(graph: Graph) -> Graph:
    """Return a new graph with unset fields filled and edge wiring propagated."""
    # Work on a deep copy so the input payload is never mutated.
    resolved = graph.model_copy(deep=True)

    # 1. Per-node field defaults (only when unset). The node's tier biases the
    # model when its name is telling; otherwise the description decides.
    for node in resolved.nodes:
        if node.model is None:
            model_id = infer_model_for_layer(node.layer) or infer_model_id(
                node.description
            )
            node.model = {"model_id": model_id}
        if node.io is None:
            node.io = _starter_io()

    # 2. Propagate caller allowlists from edges: target allows its callers.
    callers: dict[str, list[str]] = {}
    for edge in resolved.edges:
        callers.setdefault(edge.target, [])
        if edge.source not in callers[edge.target]:
            callers[edge.target].append(edge.source)

    for node in resolved.nodes:
        incoming = callers.get(node.id)
        if not incoming:
            continue
        tools = dict(node.tools) if node.tools else {}
        existing = list(tools.get("caller_allowlist", []))
        for src in incoming:
            if src not in existing:
                existing.append(src)
        tools["caller_allowlist"] = existing
        node.tools = tools

    return resolved


def resolve_node(node: GraphNode) -> GraphNode:
    """Resolve a single node's per-node defaults (no edge context)."""
    return resolve(Graph(nodes=[node])).nodes[0]
