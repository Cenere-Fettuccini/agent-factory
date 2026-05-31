"""Export a graph to a self-contained folder that depends only on the framework.

Per agent we write a frozen JSON config and a tiny loader; the package
``__init__.py`` re-exports every agent; ``_graph.json`` snapshots the graph for
round-tripping. The exported tree imports with nothing but ``agentfactory``
installed — zero runtime dependency on this API.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from composer.build import NodeBuildError, node_to_agent
from composer.network_tools import agent_edge_targets, registered_network_tools
from composer.resolver import resolve as resolve_graph
from composer.resolver import subagent_tool_id
from composer.schemas.graph import Graph, GraphNode
from composer.tool_defs import ToolDefError, registered_tools, render_tools_module


class ExportError(Exception):
    """Raised when an export cannot proceed (bad destination or invalid node)."""


class ExportResult(BaseModel):
    destination: str
    files: list[str]
    agent_ids: list[str]


_LOADER_TEMPLATE = '''"""Auto-generated loader for agent {agent_id!r}. Do not edit."""

from pathlib import Path

from agentfactory.agent import Agent

_CONFIG = Path(__file__).with_suffix(".json")


def load() -> Agent:
    """Reconstruct the frozen Agent contract from its JSON config."""
    return Agent.model_validate_json(_CONFIG.read_text(encoding="utf-8"))


agent = load()
'''


_RUNTIME_TEMPLATE = '''"""Auto-generated runtime for this exported agent network."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agentfactory.agent import Agent
from agentfactory.catalog.tools import TOOLS, ToolSpec
from agentfactory.runtime.executor import run

_ROOT = Path(__file__).resolve().parent
_GRAPH = json.loads((_ROOT / "_graph.json").read_text(encoding="utf-8"))
_SUBAGENTS: dict[str, dict[str, Any]] = __SUBAGENTS__


def _agent_path(agent_id: str) -> Path:
    for node in _GRAPH["nodes"]:
        if node["id"] != agent_id:
            continue
        module = node.get("module")
        folder = _ROOT / _package_name(module) if module else _ROOT
        return folder / f"{_module_name(agent_id)}.json"
    raise KeyError(agent_id)


def _module_name(agent_id: str) -> str:
    return agent_id.replace("-", "_")


def _package_name(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    import re

    name = re.sub(r"[^a-zA-Z0-9_]+", "_", raw.strip().lower())
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        return None
    if not re.match(r"^[a-zA-Z_]", name):
        name = f"module_{name}"
    return name


def load_agent(agent_id: str) -> Agent:
    return Agent.model_validate_json(_agent_path(agent_id).read_text(encoding="utf-8"))


async def call_agent(agent_id: str, data: dict[str, Any]) -> dict[str, Any]:
    envelope = await run(load_agent(agent_id), data)
    return envelope.data


def call_agent_sync(agent_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(call_agent(agent_id, data))


def _model_class(name: str, fields: dict[str, Any]) -> type[BaseModel]:
    from pydantic import create_model
    from agentfactory.catalog.io_types import IO_TYPES

    definitions: dict[str, Any] = {}
    for field_name, spec in fields.items():
        py_type = IO_TYPES.get(spec["type_key"]).python_type
        if spec.get("required", True):
            definitions[field_name] = (py_type, ...)
        else:
            definitions[field_name] = (py_type | None, None)
    return create_model(name, **definitions)


def _signature(fields: dict[str, Any]) -> inspect.Signature:
    return inspect.Signature(
        [
            inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            for name in fields
        ]
    )


def _register_subagent_tools() -> None:
    for agent_id, meta in _SUBAGENTS.items():
        tool_id = meta["tool_id"]
        if TOOLS.contains(tool_id):
            continue

        async def _impl(_agent_id: str = agent_id, **kwargs: Any) -> dict[str, Any]:
            return await call_agent(_agent_id, kwargs)

        _impl.__name__ = f"call_{agent_id.replace('-', '_')}"
        _impl.__signature__ = _signature(meta["input_fields"])  # type: ignore[attr-defined]

        TOOLS.register(
            tool_id,
            ToolSpec(
                id=tool_id,
                description=f"Call internal agent {agent_id}.",
                arg_schema=_model_class(f"{_impl.__name__}Args", meta["input_fields"]),
                return_schema=_model_class(f"{_impl.__name__}Result", meta["output_fields"]),
                callable=_impl,
            ),
        )


_register_subagent_tools()


async def run_entrypoint(name: str, data: dict[str, Any]) -> dict[str, Any]:
    return await call_agent(name, data)


def run_entrypoint_sync(name: str, data: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(run_entrypoint(name, data))
'''


_ENTRYPOINT_TEMPLATE = '''


async def {fn_name}(data):
    return await _runtime.run_entrypoint({agent_id!r}, data)


def {fn_name}_sync(data):
    return _runtime.run_entrypoint_sync({agent_id!r}, data)
'''


def _module_name(agent_id: str) -> str:
    return agent_id.replace("-", "_")


def _package_name(raw: str | None) -> str | None:
    """Return a safe Python/package folder name for a functional module."""
    if raw is None or not raw.strip():
        return None
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", raw.strip().lower())
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        return None
    if not re.match(r"^[a-zA-Z_]", name):
        name = f"module_{name}"
    return name


def _function_name(agent_id: str) -> str:
    name = f"run_{_module_name(agent_id)}"
    if not re.match(r"^[a-zA-Z_]", name):
        name = f"agent_{name}"
    return name


def _entrypoints(graph: Graph) -> list[tuple[str, str]]:
    """Public callable agents: explicit triggers, or top-tier agents if none."""
    entries = [
        node
        for node in graph.nodes
        if node.kind == "agent" and node.trigger is not None
    ]
    if not entries and graph.layers:
        top = graph.layers[0]
        entries = [
            node
            for node in graph.nodes
            if node.kind == "agent" and node.layer == top
        ]
    if not entries:
        entries = [node for node in graph.nodes if node.kind == "agent"]
    return [(node.id, _function_name(node.id)) for node in entries]


def _field_dump(node: GraphNode, which: str) -> dict[str, object]:
    io = node.io
    if io is None:
        return {}
    schema = io[f"{which}_schema"]
    fields: dict[str, object] = schema["fields"]
    return fields


def _render_runtime_module(graph: Graph) -> str:
    subagents = {
        node.id: {
            "tool_id": subagent_tool_id(node.id),
            "input_fields": _field_dump(node, "input"),
            "output_fields": _field_dump(node, "output"),
        }
        for node in agent_edge_targets(graph)
    }
    return _RUNTIME_TEMPLATE.replace("__SUBAGENTS__", repr(subagents))


def _guard_destination(dest: str) -> Path:
    if not dest or not dest.strip():
        raise ExportError("destination path is empty")
    path = Path(dest).expanduser()
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise ExportError(f"invalid destination path: {exc}") from exc
    # Refuse the filesystem root or a bare drive root (e.g. "/" or "C:\\").
    if resolved == resolved.parent or len(resolved.parts) <= 1:
        raise ExportError(
            f"refusing to export to a root path: {resolved}"
        )
    return resolved


def export_graph(graph: Graph, dest: str, *, overwrite: bool = False) -> ExportResult:
    """Build every agent, then write the package. Nothing is written on failure."""
    graph = resolve_graph(graph)
    destination = _guard_destination(dest)

    # Build everything up front so a bad node aborts before touching disk.
    # UI-authored tools are registered transiently so grants validate.
    built = {}
    try:
        with registered_tools(graph.tool_defs), registered_network_tools(graph):
            for node in graph.nodes:
                if node.kind == "tool":
                    continue
                try:
                    built[node.id] = node_to_agent(node)
                except NodeBuildError as exc:
                    raise ExportError(f"node {node.id!r} is invalid: {exc}") from exc
    except ToolDefError as exc:
        raise ExportError(f"authored tool is invalid: {exc}") from exc

    if destination.exists() and any(destination.iterdir()) and not overwrite:
        raise ExportError(
            f"destination {destination} is not empty (pass overwrite=True)"
        )

    destination.mkdir(parents=True, exist_ok=True)
    files: list[str] = []

    init_lines = ['"""Auto-generated agent package. Do not edit."""', ""]
    exports: list[str] = []
    module_inits: dict[str, list[str]] = {}
    module_exports: dict[str, list[str]] = {}

    # Tool stubs must register before any agent loader runs, so grants resolve.
    if graph.tool_defs:
        (destination / "_tools.py").write_text(
            render_tools_module(graph.tool_defs), encoding="utf-8"
        )
        files.append("_tools.py")
        init_lines.append("from . import _tools as _tools  # registers authored tools")

    # Always emit _runtime.py: it hosts the entrypoint runners and, when the
    # graph has call edges, also registers internal subagent tools. Gating it on
    # graph.edges left the always-emitted entrypoint functions referencing an
    # unimported module, so an edgeless export raised NameError when called.
    (destination / "_runtime.py").write_text(
        _render_runtime_module(graph), encoding="utf-8"
    )
    files.append("_runtime.py")
    init_lines.append("from . import _runtime as _runtime  # entrypoint runners + subagent tools")

    for agent_id, agent in built.items():
        module = _module_name(agent_id)
        agent_node = graph.get(agent_id)
        package = _package_name(agent_node.module if agent_node else None)
        folder = destination / package if package else destination
        folder.mkdir(parents=True, exist_ok=True)

        config_path = folder / f"{module}.json"
        config_path.write_text(agent.model_dump_json(indent=2), encoding="utf-8")
        files.append(config_path.relative_to(destination).as_posix())

        loader_path = folder / f"{module}.py"
        loader_path.write_text(
            _LOADER_TEMPLATE.format(agent_id=agent_id), encoding="utf-8"
        )
        files.append(loader_path.relative_to(destination).as_posix())

        if package:
            module_inits.setdefault(
                package, ['"""Auto-generated functional module. Do not edit."""', ""]
            )
            module_exports.setdefault(package, [])
            module_inits[package].append(f"from .{module} import agent as {module}")
            module_exports[package].append(module)
            init_lines.append(f"from .{package}.{module} import agent as {module}")
        else:
            init_lines.append(f"from .{module} import agent as {module}")
        exports.append(module)

    for package, lines in sorted(module_inits.items()):
        lines.append("")
        lines.append(f"__all__ = {sorted(module_exports[package])!r}")
        lines.append("")
        module_init = destination / package / "__init__.py"
        module_init.write_text("\n".join(lines), encoding="utf-8")
        files.append(module_init.relative_to(destination).as_posix())

    init_lines.append("")
    for agent_id, fn_name in _entrypoints(graph):
        init_lines.append(_ENTRYPOINT_TEMPLATE.format(fn_name=fn_name, agent_id=agent_id))
        exports.append(fn_name)
        exports.append(f"{fn_name}_sync")

    init_lines.append("")
    init_lines.append(f"__all__ = {sorted(exports)!r}")
    init_lines.append("")
    (destination / "__init__.py").write_text(
        "\n".join(init_lines), encoding="utf-8"
    )
    files.append("__init__.py")

    snapshot = destination / "_graph.json"
    snapshot.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    files.append("_graph.json")

    return ExportResult(
        destination=str(destination),
        files=sorted(files),
        agent_ids=list(built),
    )
