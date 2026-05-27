"""Agent executor — the runtime that walks the 7-layer contract.

Responsibilities, in order on every ``run()``:

1. Validate the request envelope against the agent's ``input_schema``.
2. Enforce ``caller_allowlist``.
3. Loop up to ``max_cycles`` cycles. Each cycle:

   a. Emit ``CycleEvent``.
   b. Check time, cost, and cycle budgets — raise if exceeded.
   c. Call the model via the injected :class:`ModelClient`.
   d. Apply retry policies from :class:`ErrorLayer` on retryable failures.
   e. If the model returned tool calls, validate each against the
      caller's ACL, dispatch via the injected :class:`ToolDispatcher`,
      and feed results back in the next cycle.
   f. Otherwise validate the proposed output against ``output_schema``
      and return :class:`AgentResponse`.

5. If cycles are exceeded, apply the configured escalation rule.
6. Fan every event out to every sink configured in :class:`LogLayer`.

The :class:`ModelClient` and :class:`ToolDispatcher` are protocols — supply
real ones (Anthropic, OpenAI, local file ops, etc.) or stubs for testing.
Nothing in this module reaches the network.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from agentfactory.core.catalog.errors import ERROR_REGISTRY
from agentfactory.core.catalog.tools import TOOL_REGISTRY
from agentfactory.core.envelope import (
    AgentError,
    AgentRequest,
    AgentResponse,
    BudgetEvent,
    CycleEvent,
    ErrorEvent,
    HITLEvent,
    ModelCallEvent,
    ToolCallEvent,
    ToolResultEvent,
    TraceContext,
    Usage,
)
from agentfactory.core.layers.logging import LogLayer
from agentfactory.runtime.sinks import Sink


# ---------------------------------------------------------------------------
# Runtime exceptions
# ---------------------------------------------------------------------------


class ExecutionError(Exception):
    """Base for everything the executor raises."""

    error_class: str = "tool_failure"


class PolicyViolation(ExecutionError):
    error_class = "policy_violation"


class BudgetExceeded(ExecutionError):
    error_class = "budget_exceeded"


# ---------------------------------------------------------------------------
# Pluggable client protocols
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelCallResult:
    """What a :class:`ModelClient` returns per call."""

    text: str | None = None
    tool_calls: tuple[tuple[str, dict[str, Any]], ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0


@dataclass(frozen=True)
class ToolCallResult:
    """What a :class:`ToolDispatcher` returns per tool invocation."""

    ok: bool
    value: Any = None
    error: str | None = None
    duration_ms: int = 0


@runtime_checkable
class ModelClient(Protocol):
    """The executor's only handle on a language model.

    Implementations bridge to the Anthropic SDK, OpenAI, local models, or a
    fake. The executor never inspects the model id beyond what :class:`ModelLayer`
    declares — clients are responsible for translating ``model_key`` into the
    right API call.
    """

    def call(
        self,
        *,
        model_key: str,
        messages: list[dict[str, Any]],
        params: dict[str, Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelCallResult: ...


@runtime_checkable
class ToolDispatcher(Protocol):
    """Resolves a tool key + args into a result.

    The executor checks ACLs *before* calling the dispatcher; the dispatcher
    is only responsible for actually doing the work. HITL tools are dispatched
    through the same interface — the executor relies on the descriptor's
    ``requires_human`` flag, not on the dispatcher, to know it should emit a
    :class:`HITLEvent`.
    """

    def call(self, *, tool_key: str, args: dict[str, Any]) -> ToolCallResult: ...


# ---------------------------------------------------------------------------
# Internal run state
# ---------------------------------------------------------------------------


@dataclass
class _RunState:
    started_at: float
    deadline: float | None
    usage: Usage = field(default_factory=Usage)
    cycle_index: int = 0
    budget_thresholds_emitted: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class AgentExecutor:
    """Synchronous executor binding an agent contract to a runtime."""

    def __init__(
        self,
        agent: LogLayer,
        *,
        model_client: ModelClient,
        tool_dispatcher: ToolDispatcher,
        sinks: list[Sink],
        depth: int = 0,
    ) -> None:
        self.agent = agent
        self.model_client = model_client
        self.tool_dispatcher = tool_dispatcher
        self.sinks = sinks
        self.depth = depth

        if self.depth > agent.max_recursion_depth:
            raise PolicyViolation(
                f"executor depth {self.depth} exceeds max_recursion_depth "
                f"{agent.max_recursion_depth}"
            )

    # --- public entry point ------------------------------------------------

    def run(self, request: AgentRequest) -> AgentResponse | AgentError:
        trace = request.trace
        try:
            self._enforce_caller(request)
            validated_input = self.agent.input_schema.validate_payload(
                request.payload, strict=self.agent.strict
            )
            state = self._init_state(request)

            messages = self._seed_messages(validated_input)

            for cycle in range(self.agent.max_cycles):
                state.cycle_index = cycle
                state.usage = state.usage.model_copy(update={"cycles": cycle + 1})
                self._emit(CycleEvent(agent_id=self.agent.id, trace=trace, cycle_index=cycle))
                self._check_budgets(state, trace)

                model_result = self._call_model(state, trace, messages)

                if model_result.tool_calls:
                    self._dispatch_tools(
                        request, state, trace, messages, model_result.tool_calls
                    )
                    continue

                # No tool calls -> attempt to finalize.
                payload = self._coerce_output(model_result)
                validated_output = self.agent.output_schema.validate_payload(
                    payload, strict=self.agent.strict
                )
                return AgentResponse(
                    request_id=request.request_id,
                    agent_id=self.agent.id,
                    payload=validated_output,
                    usage=state.usage,
                    trace=trace,
                )

            # Cycles exhausted.
            return self._handle_cycles_exceeded(request, state, trace)

        except ExecutionError as e:
            return self._error_from_exception(request, trace, e)
        except ValueError as e:
            # Schema validation errors land here.
            return self._error(
                request, trace, "validation_error", str(e), retryable=False
            )

    # --- request validation ------------------------------------------------

    def _enforce_caller(self, request: AgentRequest) -> None:
        allowed = self.agent.allowed_tools_for(request.caller_id)
        # If caller_allowlist is set and caller is absent, allowed_tools_for
        # returns an empty set — but the agent itself is still unreachable.
        if (
            self.agent.caller_allowlist is not None
            and request.caller_id not in self.agent.caller_allowlist
        ):
            raise PolicyViolation(
                f"caller {request.caller_id!r} is not in caller_allowlist"
            )
        # Stash the per-caller allowed-tool set for later ACL checks.
        self._caller_allowed_tools = allowed

    # --- budgets -----------------------------------------------------------

    def _init_state(self, request: AgentRequest) -> _RunState:
        started = time.monotonic()
        deadline_ts: float | None = None
        if request.deadline is not None:
            deadline_ts = request.deadline.timestamp()
        # time_budget caps wall-clock; whichever is tighter applies.
        time_cap = started + self.agent.time_budget.total_seconds
        if deadline_ts is None or time_cap < deadline_ts:
            deadline_ts = time_cap
        return _RunState(started_at=started, deadline=deadline_ts)

    def _check_budgets(self, state: _RunState, trace: TraceContext) -> None:
        # Time budget.
        if state.deadline is not None and time.monotonic() >= state.deadline:
            self._emit(
                BudgetEvent(
                    agent_id=self.agent.id, trace=trace,
                    metric="time", used=time.monotonic() - state.started_at,
                    limit=self.agent.time_budget.total_seconds,
                    threshold="exhausted",
                )
            )
            raise BudgetExceeded("time budget exhausted")

        # Cost budget — emit milestones at 80% and exhaustion.
        budget = self.agent.cost_budget_usd
        used = state.usage.cost_usd
        if budget > 0:
            pct = used / budget
            if pct >= 1.0:
                self._emit(
                    BudgetEvent(
                        agent_id=self.agent.id, trace=trace, metric="cost",
                        used=used, limit=budget, threshold="exhausted",
                    )
                )
                raise BudgetExceeded(f"cost budget {budget} exhausted at {used}")
            if pct >= 0.8 and "cost_80pct" not in state.budget_thresholds_emitted:
                state.budget_thresholds_emitted.add("cost_80pct")
                self._emit(
                    BudgetEvent(
                        agent_id=self.agent.id, trace=trace, metric="cost",
                        used=used, limit=budget, threshold="80pct",
                    )
                )

    # --- model call --------------------------------------------------------

    def _call_model(
        self,
        state: _RunState,
        trace: TraceContext,
        messages: list[dict[str, Any]],
    ) -> ModelCallResult:
        candidates = self.agent.candidate_models()
        last_error: Exception | None = None
        for model_key in candidates:
            params = self.agent.generation_params.model_dump()
            try:
                result = self.model_client.call(
                    model_key=model_key,
                    messages=messages,
                    params=params,
                    tools=self._tool_specs(),
                )
            except Exception as e:  # noqa: BLE001 — we re-raise after classification
                last_error = e
                err_class = _classify_exception(e)
                self._emit(ErrorEvent(
                    agent_id=self.agent.id, trace=trace,
                    error_class=err_class, message=str(e), handled=True,
                ))
                if not self._should_retry(err_class):
                    raise ExecutionError(f"model call failed: {e}") from e
                continue

            self._emit(ModelCallEvent(
                agent_id=self.agent.id, trace=trace,
                model_key=model_key,
                input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                duration_ms=result.duration_ms, cost_usd=result.cost_usd,
            ))
            state.usage = state.usage.model_copy(update={
                "input_tokens": state.usage.input_tokens + result.input_tokens,
                "output_tokens": state.usage.output_tokens + result.output_tokens,
                "cost_usd": state.usage.cost_usd + result.cost_usd,
                "duration_ms": state.usage.duration_ms + result.duration_ms,
                "model_calls": state.usage.model_calls + 1,
            })
            return result

        # All candidates exhausted.
        raise ExecutionError(
            f"all {len(candidates)} model candidates failed; last: {last_error}"
        )

    def _should_retry(self, error_class: str) -> bool:
        return error_class in self.agent.retry_policies

    def _tool_specs(self) -> list[dict[str, Any]] | None:
        if not self.agent.tool_grants:
            return None
        specs: list[dict[str, Any]] = []
        for key in sorted(self.agent.tool_grants):
            desc = TOOL_REGISTRY.get(key)
            specs.append({
                "name": key,
                "description": desc.description,
                "requires_human": desc.requires_human,
            })
        return specs

    # --- tool dispatch -----------------------------------------------------

    def _dispatch_tools(
        self,
        request: AgentRequest,
        state: _RunState,
        trace: TraceContext,
        messages: list[dict[str, Any]],
        calls: tuple[tuple[str, dict[str, Any]], ...],
    ) -> None:
        for tool_key, args in calls:
            # Resolve alias if any.
            resolved = self.agent.aliases.get(tool_key, tool_key)
            if resolved not in self.agent.tool_grants:
                raise PolicyViolation(
                    f"tool {resolved!r} is not in tool_grants"
                )
            if resolved not in self._caller_allowed_tools:
                raise PolicyViolation(
                    f"caller {request.caller_id!r} is not permitted to call "
                    f"tool {resolved!r}"
                )

            desc = TOOL_REGISTRY.get(resolved)
            merged_args = {**self.agent.defaults.get(resolved, {}), **args}

            self._emit(ToolCallEvent(
                agent_id=self.agent.id, trace=trace,
                tool_key=resolved, args=merged_args,
            ))
            if desc.requires_human:
                self._emit(HITLEvent(
                    agent_id=self.agent.id, trace=trace,
                    tool_key=resolved, phase="requested",
                ))

            result = self.tool_dispatcher.call(tool_key=resolved, args=merged_args)
            state.usage = state.usage.model_copy(update={
                "tool_calls": state.usage.tool_calls + 1,
                "duration_ms": state.usage.duration_ms + result.duration_ms,
            })
            self._emit(ToolResultEvent(
                agent_id=self.agent.id, trace=trace,
                tool_key=resolved, ok=result.ok,
                duration_ms=result.duration_ms, error=result.error,
            ))
            if desc.requires_human:
                self._emit(HITLEvent(
                    agent_id=self.agent.id, trace=trace,
                    tool_key=resolved,
                    phase="responded" if result.ok else "denied",
                ))
            messages.append({
                "role": "tool",
                "tool_key": resolved,
                "ok": result.ok,
                "value": result.value,
                "error": result.error,
            })

    # --- output / errors ---------------------------------------------------

    def _seed_messages(self, validated_input: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"role": "user", "content": validated_input}]

    def _coerce_output(self, result: ModelCallResult) -> dict[str, Any]:
        # Convention: when the output schema has exactly one text field, treat
        # the model's text as that field. Otherwise expect the model to return
        # a structured payload via a tool call shape (left to extensions).
        text_fields = [
            fname for fname, spec in self.agent.output_schema.fields.items()
            if spec.type_key == "text" and not spec.repeated
        ]
        if len(text_fields) == 1 and result.text is not None:
            return {text_fields[0]: result.text}
        raise ExecutionError(
            "executor cannot map model output to schema without explicit "
            "structured output handling; supply a custom executor"
        )

    def _handle_cycles_exceeded(
        self, request: AgentRequest, state: _RunState, trace: TraceContext
    ) -> AgentResponse | AgentError:
        # Find a matching escalation rule.
        for rule in self.agent.escalation_rules:
            if rule.trigger == "cycles_exceeded":
                if rule.action == "log_only":
                    self._emit(ErrorEvent(
                        agent_id=self.agent.id, trace=trace,
                        error_class="policy_violation",
                        message="cycles exceeded; logging only",
                        handled=True,
                    ))
                    break
                if rule.action == "raise":
                    break  # fall through to default raise
                # fallback / human_review are out of scope for the skeleton.
                break
        return self._error(
            request, trace, "policy_violation",
            f"max_cycles={self.agent.max_cycles} exceeded",
            retryable=False,
        )

    def _error_from_exception(
        self, request: AgentRequest, trace: TraceContext, e: ExecutionError
    ) -> AgentError:
        return self._error(request, trace, e.error_class, str(e), retryable=False)

    def _error(
        self,
        request: AgentRequest,
        trace: TraceContext,
        error_class: str,
        message: str,
        *,
        retryable: bool,
    ) -> AgentError:
        # Defensive: error_class should always be in the registry.
        if not ERROR_REGISTRY.has(error_class):
            error_class = "tool_failure"
        self._emit(ErrorEvent(
            agent_id=self.agent.id, trace=trace,
            error_class=error_class, message=message, handled=False,
        ))
        return AgentError(
            request_id=request.request_id,
            agent_id=self.agent.id,
            error_class=error_class,
            message=message,
            retryable=retryable,
            trace=trace,
        )

    # --- sink fan-out ------------------------------------------------------

    def _emit(self, event: BaseModel) -> None:
        for sink in self.sinks:
            try:
                sink.emit(event)
            except Exception:
                # Sinks must never break the run. Swallow.
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_exception(e: BaseException) -> str:
    """Map a raw exception onto an ERROR_REGISTRY key by name heuristics.

    A real ModelClient would translate provider exceptions into these classes
    before raising; this fallback exists so the executor still behaves sanely
    when bridged to a less careful client.
    """
    name = type(e).__name__.lower()
    if "rate" in name and "limit" in name:
        return "rate_limit"
    if "timeout" in name:
        return "timeout"
    if "validation" in name or isinstance(e, ValueError):
        return "validation_error"
    return "model_failure"
