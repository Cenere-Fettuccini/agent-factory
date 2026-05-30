"""Export a graph to a self-contained folder that depends only on the framework.

Per agent we write a frozen JSON config and a tiny loader; the package
``__init__.py`` re-exports every agent; ``_graph.json`` snapshots the graph for
round-tripping. The exported tree imports with nothing but ``agentfactory``
installed — zero runtime dependency on this API.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from composer.build import NodeBuildError, node_to_agent
from composer.schemas.graph import Graph
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


def _module_name(agent_id: str) -> str:
    return agent_id.replace("-", "_")


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
    destination = _guard_destination(dest)

    # Build everything up front so a bad node aborts before touching disk.
    # UI-authored tools are registered transiently so grants validate.
    built = {}
    try:
        with registered_tools(graph.tool_defs):
            for node in graph.nodes:
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

    # Tool stubs must register before any agent loader runs, so grants resolve.
    if graph.tool_defs:
        (destination / "_tools.py").write_text(
            render_tools_module(graph.tool_defs), encoding="utf-8"
        )
        files.append("_tools.py")
        init_lines.append("from . import _tools as _tools  # registers authored tools")

    for agent_id, agent in built.items():
        module = _module_name(agent_id)

        config_path = destination / f"{module}.json"
        config_path.write_text(agent.model_dump_json(indent=2), encoding="utf-8")
        files.append(config_path.name)

        loader_path = destination / f"{module}.py"
        loader_path.write_text(
            _LOADER_TEMPLATE.format(agent_id=agent_id), encoding="utf-8"
        )
        files.append(loader_path.name)

        init_lines.append(f"from .{module} import agent as {module}")
        exports.append(module)

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
