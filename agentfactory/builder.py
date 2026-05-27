"""Fluent builder for assembling an :class:`Agent`.

The keyword-arg constructor on :class:`agentfactory.LogLayer` is fine for
fully-known configurations, but config-driven or progressive setups often
want to add layers one step at a time. :class:`AgentBuilder` provides that:

    Agent = (AgentBuilder("summarizer-v1", name="Summarizer", version="0.1.0",
                          description="Summarises short text.")
              .with_model(CoreModel.HAIKU_4_5.value)
              .with_io(input_schema=inp, output_schema=out)
              .with_tools("read_file", aliases={"open": "read_file"})
              .with_policy(max_cycles=5, cost_budget_usd=0.10)
              .with_errors(retry_policies={"rate_limit": RetryPolicy()})
              .with_logging(primary_sink="stdout")
              .build())

Calling ``build()`` constructs and returns a frozen :class:`Agent` with all
construction-time validation applied. Each ``with_*`` step is additive — call
it once or many times; later calls overwrite earlier values for the same slot.
"""

from __future__ import annotations

from typing import Any, Self

from agentfactory import Agent
from agentfactory.core.layers.errors import (
    CircuitBreaker,
    EscalationRule,
    PartialResultPolicy,
    RetryPolicy,
)
from agentfactory.core.layers.io import IOSchema
from agentfactory.core.layers.logging import RedactionRule, SamplingRule
from agentfactory.core.layers.model import (
    CacheStrategy,
    GenerationParams,
    RoutingPolicy,
)
from agentfactory.core.layers.policy import RateLimit, TimeBudget


class AgentBuilder:
    """Mutable, fluent builder for an :class:`Agent`.

    The builder collects per-layer kwargs and forwards them to the Agent
    constructor in ``build()``. All Pydantic validation runs there — the
    builder itself does not validate.
    """

    def __init__(
        self,
        agent_id: str,
        *,
        name: str,
        version: str,
        description: str,
        tags: frozenset[str] | list[str] | tuple[str, ...] = (),
    ) -> None:
        self._fields: dict[str, Any] = {
            "id": agent_id,
            "name": name,
            "version": version,
            "description": description,
            "tags": tags,
        }

    # --- per-layer setters ------------------------------------------------

    def with_model(
        self,
        primary: str,
        *,
        fallback_chain: tuple[str, ...] | list[str] = (),
        routing_policy: RoutingPolicy | None = None,
        generation_params: GenerationParams | None = None,
        cache_strategy: CacheStrategy | None = None,
    ) -> Self:
        self._fields["primary"] = primary
        self._fields["fallback_chain"] = tuple(fallback_chain)
        if routing_policy is not None:
            self._fields["routing_policy"] = routing_policy
        if generation_params is not None:
            self._fields["generation_params"] = generation_params
        if cache_strategy is not None:
            self._fields["cache_strategy"] = cache_strategy
        return self

    def with_io(
        self,
        *,
        input_schema: IOSchema,
        output_schema: IOSchema,
        strict: bool | None = None,
        encoding: str | None = None,
        streaming_mode: str | None = None,
    ) -> Self:
        self._fields["input_schema"] = input_schema
        self._fields["output_schema"] = output_schema
        if strict is not None:
            self._fields["strict"] = strict
        if encoding is not None:
            self._fields["encoding"] = encoding
        if streaming_mode is not None:
            self._fields["streaming_mode"] = streaming_mode
        return self

    def with_tools(
        self,
        *tool_keys: str,
        subagents: frozenset[str] | list[str] | tuple[str, ...] = (),
        aliases: dict[str, str] | None = None,
        defaults: dict[str, dict[str, Any]] | None = None,
    ) -> Self:
        self._fields["tool_grants"] = frozenset(tool_keys)
        self._fields["subagent_grants"] = frozenset(subagents)
        if aliases is not None:
            self._fields["aliases"] = dict(aliases)
        if defaults is not None:
            self._fields["defaults"] = {k: dict(v) for k, v in defaults.items()}
        return self

    def with_policy(
        self,
        *,
        caller_allowlist: frozenset[str] | list[str] | None = None,
        tool_acl: dict[str, frozenset[str] | list[str]] | None = None,
        max_cycles: int | None = None,
        max_recursion_depth: int | None = None,
        cost_budget_usd: float | None = None,
        rate_limit: RateLimit | None = None,
        time_budget: TimeBudget | None = None,
    ) -> Self:
        if caller_allowlist is not None:
            self._fields["caller_allowlist"] = frozenset(caller_allowlist)
        if tool_acl is not None:
            self._fields["tool_acl"] = {
                k: frozenset(v) for k, v in tool_acl.items()
            }
        if max_cycles is not None:
            self._fields["max_cycles"] = max_cycles
        if max_recursion_depth is not None:
            self._fields["max_recursion_depth"] = max_recursion_depth
        if cost_budget_usd is not None:
            self._fields["cost_budget_usd"] = cost_budget_usd
        if rate_limit is not None:
            self._fields["rate_limit"] = rate_limit
        if time_budget is not None:
            self._fields["time_budget"] = time_budget
        return self

    def with_errors(
        self,
        *,
        retry_policies: dict[str, RetryPolicy] | None = None,
        fallback_agent: str | None = None,
        escalation_rules: tuple[EscalationRule, ...] | list[EscalationRule] | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        compensation_actions: dict[str, str] | None = None,
        partial_result_policy: PartialResultPolicy | None = None,
    ) -> Self:
        if retry_policies is not None:
            self._fields["retry_policies"] = dict(retry_policies)
        if fallback_agent is not None:
            self._fields["fallback_agent"] = fallback_agent
        if escalation_rules is not None:
            self._fields["escalation_rules"] = tuple(escalation_rules)
        if circuit_breaker is not None:
            self._fields["circuit_breaker"] = circuit_breaker
        if compensation_actions is not None:
            self._fields["compensation_actions"] = dict(compensation_actions)
        if partial_result_policy is not None:
            self._fields["partial_result_policy"] = partial_result_policy
        return self

    def with_logging(
        self,
        primary_sink: str = "null",
        *,
        secondary_sinks: tuple[str, ...] | list[str] = (),
        sink_configs: dict[str, dict[str, Any]] | None = None,
        sampling: SamplingRule | None = None,
        redaction: RedactionRule | None = None,
        trace_context_enabled: bool | None = None,
    ) -> Self:
        self._fields["primary_sink"] = primary_sink
        self._fields["secondary_sinks"] = tuple(secondary_sinks)
        if sink_configs is not None:
            self._fields["sink_configs"] = {
                k: dict(v) for k, v in sink_configs.items()
            }
        if sampling is not None:
            self._fields["sampling"] = sampling
        if redaction is not None:
            self._fields["redaction"] = redaction
        if trace_context_enabled is not None:
            self._fields["trace_context_enabled"] = trace_context_enabled
        return self

    # --- finalization ------------------------------------------------------

    def build(self) -> Agent:
        """Construct the Agent. Raises Pydantic ValidationError on bad config."""
        return Agent(**self._fields)
