"""Core tool catalog.

A tool is anything the agent can reach out and invoke — a file read, an API
call, *or a human*. HITL tools live in the same registry as ordinary tools
and are distinguished only by the ``requires_human`` flag on their descriptor.
This collapses approval / clarification / review into the same call shape as
any other tool, keeping the layer above (ToolLayer) uniform.

Each descriptor declares its parameter schema and return schema as
:class:`IOSchema` instances drawn from the IO lexicon, so a caller can
type-check a tool invocation before dispatching it.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentfactory.core.catalog.io_lexicon import IOFieldSpec, IOSchema
from agentfactory.core.registry import Registry


class ToolDescriptor(BaseModel):
    """One catalog entry describing a callable tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["tool"] = "tool"
    key: str = Field(..., min_length=1, max_length=64)
    description: str = Field(default="", max_length=512)

    # Optional schemas. ``None`` means the tool takes no arguments / returns
    # no value (e.g. ``human_acknowledge`` returns nothing meaningful).
    parameters: IOSchema | None = None
    returns: IOSchema | None = None

    requires_human: bool = Field(
        default=False,
        description="True for HITL tools — the executor routes the call to a human.",
    )
    side_effects: tuple[str, ...] = Field(
        default_factory=tuple,
        description=(
            "Declared side effects in coarse categories: 'read_fs', 'write_fs', "
            "'network', 'spawn_process', 'human_io'. Used by PolicyLayer."
        ),
    )


TOOL_REGISTRY: Final[Registry[ToolDescriptor]] = Registry(
    kind="tool", component_type=ToolDescriptor
)


# ---------------------------------------------------------------------------
# Core entries
# ---------------------------------------------------------------------------


def _schema(name: str, **fields: IOFieldSpec) -> IOSchema:
    return IOSchema(name=name, fields=fields)


def _bootstrap_core() -> None:
    core: tuple[ToolDescriptor, ...] = (
        # --- ordinary tools -------------------------------------------------
        ToolDescriptor(
            key="read_file",
            description="Read a file from the local filesystem.",
            parameters=_schema(
                "ReadFileArgs", path=IOFieldSpec(type_key="file_ref")
            ),
            returns=_schema("ReadFileResult", content=IOFieldSpec(type_key="text")),
            side_effects=("read_fs",),
        ),
        ToolDescriptor(
            key="glob",
            description="Find files by glob pattern.",
            parameters=_schema("GlobArgs", pattern=IOFieldSpec(type_key="text")),
            returns=_schema(
                "GlobResult",
                paths=IOFieldSpec(type_key="file_ref", repeated=True),
            ),
            side_effects=("read_fs",),
        ),
        ToolDescriptor(
            key="grep",
            description="Search file contents by regex.",
            parameters=_schema(
                "GrepArgs",
                pattern=IOFieldSpec(type_key="text"),
                path=IOFieldSpec(type_key="file_ref", required=False),
            ),
            returns=_schema(
                "GrepResult", matches=IOFieldSpec(type_key="text", repeated=True)
            ),
            side_effects=("read_fs",),
        ),
        # --- HITL tools (requires_human=True) ------------------------------
        ToolDescriptor(
            key="human_review",
            description="Pause for a human to review a proposed action or output.",
            parameters=_schema(
                "HumanReviewArgs",
                subject=IOFieldSpec(type_key="text"),
                context=IOFieldSpec(type_key="text", required=False),
            ),
            returns=_schema(
                "HumanReviewResult",
                feedback=IOFieldSpec(type_key="text"),
            ),
            requires_human=True,
            side_effects=("human_io",),
        ),
        ToolDescriptor(
            key="human_approve",
            description="Request a human approve/deny decision.",
            parameters=_schema(
                "HumanApproveArgs",
                question=IOFieldSpec(type_key="text"),
                rationale=IOFieldSpec(type_key="text", required=False),
            ),
            returns=_schema(
                "HumanApproveResult", decision=IOFieldSpec(type_key="decision")
            ),
            requires_human=True,
            side_effects=("human_io",),
        ),
        ToolDescriptor(
            key="human_input",
            description="Ask a human for free-form input.",
            parameters=_schema(
                "HumanInputArgs", prompt=IOFieldSpec(type_key="text")
            ),
            returns=_schema(
                "HumanInputResult", response=IOFieldSpec(type_key="text")
            ),
            requires_human=True,
            side_effects=("human_io",),
        ),
    )
    for entry in core:
        TOOL_REGISTRY._register_core(entry)
    TOOL_REGISTRY.seal_core()


_bootstrap_core()
