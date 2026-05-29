"""Catalog of telemetry sinks. Descriptive only — no exporter is imported here."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentfactory.catalog.registry import Registry

SinkKind = Literal["otlp_http", "otlp_grpc", "console", "noop"]


class SinkSpec(BaseModel):
    """A descriptive telemetry sink. Host apps wire the actual exporter."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: SinkKind
    endpoint: str | None = None


SINKS: Registry[SinkSpec] = Registry("sink")


def seed_defaults() -> None:
    if SINKS.ids():
        return
    SINKS.register("console", SinkSpec(id="console", kind="console"))
    SINKS.register("noop", SinkSpec(id="noop", kind="noop"))
