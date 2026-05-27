"""Core log-sink catalog.

A sink is a destination for :class:`LogEvent` records emitted by the executor.
The catalog ships four core sinks: ``null``, ``stdout``, ``file``, ``langfuse``.
Each :class:`SinkDescriptor` declares its configuration shape as an
:class:`IOSchema` (or ``None`` for parameter-free sinks); the LogLayer then
validates user-supplied per-sink config against that schema.

The descriptor itself is config-free; instantiation of the *actual* sink
object (e.g. opening a file handle, connecting to Langfuse) happens at
executor startup using the agent's ``sink_configs`` entries.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentfactory.core.catalog.io_lexicon import IOFieldSpec, IOSchema
from agentfactory.core.registry import Registry


class SinkDescriptor(BaseModel):
    """One catalog entry describing an available log sink."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["log"] = "log"
    key: str = Field(..., min_length=1, max_length=64)
    description: str = Field(default="", max_length=512)

    config_schema: IOSchema | None = Field(
        default=None,
        description="IOSchema describing this sink's config shape, or None.",
    )
    requires_network: bool = Field(
        default=False,
        description="True if this sink reaches the network (used by audits).",
    )


SINK_REGISTRY: Final[Registry[SinkDescriptor]] = Registry(
    kind="log", component_type=SinkDescriptor
)


def _bootstrap_core() -> None:
    core: tuple[SinkDescriptor, ...] = (
        SinkDescriptor(
            key="null",
            description="Discard all events. Useful as a stand-in default.",
        ),
        SinkDescriptor(
            key="stdout",
            description="Write JSON lines to process stdout.",
        ),
        SinkDescriptor(
            key="file",
            description="Append JSON lines to a local file.",
            config_schema=IOSchema(
                name="FileSinkConfig",
                fields={
                    "path": IOFieldSpec(type_key="file_ref"),
                    "rotate_mb": IOFieldSpec(
                        type_key="integer", required=False
                    ),
                },
            ),
        ),
        SinkDescriptor(
            key="langfuse",
            description="Upload events to Langfuse for tracing and observability.",
            config_schema=IOSchema(
                name="LangfuseSinkConfig",
                fields={
                    "public_key": IOFieldSpec(type_key="text"),
                    "secret_key": IOFieldSpec(type_key="text"),
                    "host": IOFieldSpec(type_key="text", required=False),
                    "project": IOFieldSpec(type_key="text", required=False),
                },
            ),
            requires_network=True,
        ),
    )
    for entry in core:
        SINK_REGISTRY._register_core(entry)
    SINK_REGISTRY.seal_core()


_bootstrap_core()
