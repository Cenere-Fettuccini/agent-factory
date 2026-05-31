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


# Default per-tool call cap used to size the global tool-call budget when an edge
# carries no explicit cap. Mirrors DEFAULT_CALL_CAP in the studio-web store.
DEFAULT_CALL_CAP = 3
# Fallback recursion depth when the subagent graph reachable from a node contains
# a cycle (no finite longest chain). Mirrors graph_validation.DEFAULT_MAX_RECURSION.
DEFAULT_MAX_RECURSION = 2


def subagent_tool_id(agent_id: str) -> str:
    """Catalog id used when one agent calls another exported agent."""
    return f"agentfactory.subagent.{agent_id}"


class _CycleError(Exception):
    """Internal: the subagent graph has a cycle, so depth isn't a finite chain."""


def _subagent_adjacency(graph: Graph) -> dict[str, list[str]]:
    """Adjacency over agent->agent (subagent) edges only; tool edges are excluded."""
    kinds = {n.id: n.kind for n in graph.nodes}
    adj: dict[str, list[str]] = {}
    for edge in graph.edges:
        if kinds.get(edge.source) == "agent" and kinds.get(edge.target) == "agent":
            adj.setdefault(edge.source, []).append(edge.target)
    return adj


def _longest_chain(start: str, adj: dict[str, list[str]]) -> int:
    """Longest number of subagent edges on any path from ``start``.

    Raises _CycleError if a cycle is reachable (no finite longest path).
    """
    memo: dict[str, int] = {}
    on_stack: set[str] = set()

    def dfs(node: str) -> int:
        if node in on_stack:
            raise _CycleError
        if node in memo:
            return memo[node]
        on_stack.add(node)
        best = 0
        for nxt in adj.get(node, []):
            best = max(best, 1 + dfs(nxt))
        on_stack.discard(node)
        memo[node] = best
        return best

    return dfs(start)


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
        if node.kind == "tool":
            continue
        if node.model is None:
            model_id = infer_model_for_layer(node.layer) or infer_model_id(
                node.description
            )
            node.model = {"model_id": model_id}
        if node.io is None:
            node.io = _starter_io()

    # 2. Propagate edge-derived wiring. Agent targets allow their callers and
    # become callable as internal subagent tools. Tool-node targets grant their
    # owned functions to the caller agent.
    callers: dict[str, list[str]] = {}
    grants: dict[str, list[str]] = {}
    node_kinds = {node.id: node.kind for node in resolved.nodes}
    tools_by_node: dict[str, list[str]] = {}
    for td in resolved.tool_defs:
        if td.node_id:
            tools_by_node.setdefault(td.node_id, []).append(td.id)

    for edge in resolved.edges:
        if node_kinds.get(edge.target) == "tool":
            for tool_id in tools_by_node.get(edge.target, []):
                grants.setdefault(edge.source, [])
                if tool_id not in grants[edge.source]:
                    grants[edge.source].append(tool_id)
        else:
            callers.setdefault(edge.target, [])
            if edge.source not in callers[edge.target]:
                callers[edge.target].append(edge.source)
            grants.setdefault(edge.source, [])
            tool_id = subagent_tool_id(edge.target)
            if tool_id not in grants[edge.source]:
                grants[edge.source].append(tool_id)

    for node in resolved.nodes:
        if node.kind == "tool":
            continue
        incoming = callers.get(node.id)
        tools = dict(node.tools) if node.tools else {}
        changed = False
        if incoming:
            existing = list(tools.get("caller_allowlist", []))
            for src in incoming:
                if src not in existing:
                    existing.append(src)
            tools["caller_allowlist"] = existing
            changed = True
        node_grants = grants.get(node.id)
        if node_grants:
            existing_grants = list(tools.get("tool_grants", []))
            for tool_id in node_grants:
                if tool_id not in existing_grants:
                    existing_grants.append(tool_id)
            tools["tool_grants"] = existing_grants
            changed = True
        if changed:
            node.tools = tools

    # 3. Infer per-node policy budgets from topology (only when the author left
    # policy unset). These are derivable from the graph, so the UI never has to
    # ask for them:
    #   max_recursion_depth — longest subagent chain reachable from the node
    #                         (a cycle falls back to a safe default).
    #   max_tool_calls      — sum of each grant's cap (explicit, or the default),
    #                         so the global budget matches the per-tool caps.
    #   max_steps           — enough model turns to actually spend that budget.
    adj = _subagent_adjacency(resolved)
    for node in resolved.nodes:
        if node.kind == "tool" or node.policy is not None:
            continue
        tools = node.tools or {}
        grant_ids = list(tools.get("tool_grants", []))
        caps = dict(tools.get("tool_call_caps", {}))

        try:
            chain = _longest_chain(node.id, adj)
        except _CycleError:
            chain = DEFAULT_MAX_RECURSION
        policy: dict[str, object] = {"max_recursion_depth": max(1, chain)}

        if grant_ids:
            max_tool_calls = sum(caps.get(t, DEFAULT_CALL_CAP) for t in grant_ids)
            policy["max_tool_calls"] = max_tool_calls
            # The model needs a turn to read each tool result, plus one to answer.
            policy["max_steps"] = max(8, max_tool_calls + 1)

        node.policy = policy

    return resolved


def resolve_node(node: GraphNode) -> GraphNode:
    """Resolve a single node's per-node defaults (no edge context)."""
    return resolve(Graph(nodes=[node])).nodes[0]
