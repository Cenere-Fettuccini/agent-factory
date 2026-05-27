"""Concrete sink implementations for the four core sink descriptors.

Sinks accept :data:`agentfactory.core.envelope.AgentEvent` records and route
them somewhere durable (or nowhere, for :class:`NullSinkImpl`). The executor
holds a list of these and fans every event out to all of them.

These are intentionally minimal: ``LangfuseSinkImpl`` is a stub that prints
what it *would* upload, so the framework has no hard dependency on the
``langfuse`` package. Swap in a real implementation by subclassing.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class Sink(Protocol):
    """Runtime sink interface. Implementations must be thread-safe."""

    key: str

    def emit(self, event: BaseModel) -> None: ...
    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


class NullSinkImpl:
    """Discards every event. Used as the default when no observability is wanted."""

    key = "null"

    def emit(self, event: BaseModel) -> None:
        return None

    def close(self) -> None:
        return None


class StdoutSinkImpl:
    """Writes JSON lines to process stdout. Thread-safe via a print lock."""

    key = "stdout"

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def emit(self, event: BaseModel) -> None:
        line = event.model_dump_json()
        with self._lock:
            print(line, file=sys.stdout, flush=False)

    def close(self) -> None:
        sys.stdout.flush()


class FileSinkImpl:
    """Appends JSON lines to a file. Rotates by size when ``rotate_mb`` is set."""

    key = "file"

    def __init__(self, path: str, rotate_mb: int | None = None) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._rotate_bytes = rotate_mb * 1024 * 1024 if rotate_mb else None
        self._lock = threading.Lock()
        # Open lazily so construction never fails on permission checks.
        self._fp = None

    def _open(self) -> Any:
        if self._fp is None:
            self._fp = self._path.open("a", encoding="utf-8")
        return self._fp

    def _maybe_rotate(self) -> None:
        if self._rotate_bytes is None:
            return
        if not self._path.exists():
            return
        if self._path.stat().st_size < self._rotate_bytes:
            return
        if self._fp is not None:
            self._fp.close()
            self._fp = None
        rotated = self._path.with_suffix(self._path.suffix + ".1")
        os.replace(self._path, rotated)

    def emit(self, event: BaseModel) -> None:
        line = event.model_dump_json() + "\n"
        with self._lock:
            self._maybe_rotate()
            fp = self._open()
            fp.write(line)
            fp.flush()

    def close(self) -> None:
        with self._lock:
            if self._fp is not None:
                self._fp.close()
                self._fp = None


class LangfuseSinkImpl:
    """Stub Langfuse sink.

    Real integration would import ``langfuse`` and build trace/span/event
    objects from each :class:`AgentEvent`. This stub captures what *would*
    be uploaded — useful for tests and for keeping the framework
    dependency-free at the core level. Replace with a real subclass when
    deploying.
    """

    key = "langfuse"

    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        host: str | None = None,
        project: str | None = None,
    ) -> None:
        if not public_key or not secret_key:
            raise ValueError("LangfuseSinkImpl requires public_key and secret_key")
        self._public_key = public_key
        self._secret_key = secret_key
        self._host = host or "https://cloud.langfuse.com"
        self._project = project
        self.captured: list[dict[str, Any]] = []  # for inspection in tests

    def emit(self, event: BaseModel) -> None:
        # Real impl: langfuse.trace(...).span(...).event(...). Stub captures.
        self.captured.append(event.model_dump(mode="json"))

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_sink(key: str, config: dict[str, Any] | None = None) -> Sink:
    """Instantiate the concrete sink for a SINK_REGISTRY key.

    The mapping here is deliberately closed — subclasses or registered
    extension sinks must provide their own factory. Keeping this small means
    the runtime never silently picks an unexpected implementation.
    """
    cfg = config or {}
    if key == "null":
        return NullSinkImpl()
    if key == "stdout":
        return StdoutSinkImpl()
    if key == "file":
        return FileSinkImpl(**cfg)
    if key == "langfuse":
        return LangfuseSinkImpl(**cfg)
    raise ValueError(
        f"no built-in sink implementation for key {key!r}; "
        f"subclass Sink and instantiate it directly"
    )
