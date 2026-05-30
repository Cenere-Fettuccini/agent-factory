"""Tests for UI-authored tool definitions: materialisation, scope, export."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from agentfactory.catalog.tools import TOOLS, ToolSpec
from composer.export import export_graph
from composer.preview import dry_run, preview_agent
from composer.resolver import resolve
from composer.schemas.graph import Graph, GraphNode, ToolDef
from composer.tool_defs import (
    ToolDefError,
    registered_tools,
    tool_def_to_spec,
    validate_tool_def,
)


def _search_tool() -> ToolDef:
    return ToolDef.model_validate(
        {
            "id": "web-search",
            "description": "Search the web.",
            "args": {"query": {"type_key": "text"}},
            "returns": {"results": {"type_key": "json"}},
        }
    )


def test_tool_def_to_spec_builds_real_spec() -> None:
    spec = tool_def_to_spec(_search_tool())
    assert isinstance(spec, ToolSpec)
    assert spec.id == "web-search"
    # arg_schema is a real Pydantic model with the declared field.
    assert "query" in spec.arg_schema.model_json_schema()["properties"]
    assert spec.return_schema is not None


def test_stub_callable_raises_not_implemented() -> None:
    spec = tool_def_to_spec(_search_tool())
    with pytest.raises(NotImplementedError, match="web-search"):
        spec.callable(query="hi")


def test_bad_tool_id_rejected() -> None:
    with pytest.raises(ToolDefError, match="must match"):
        tool_def_to_spec(ToolDef(id="Bad Id"))


def test_unknown_type_key_rejected() -> None:
    bad = ToolDef.model_validate(
        {"id": "t", "args": {"x": {"type_key": "nope"}}}
    )
    with pytest.raises(ToolDefError, match="lexicon"):
        tool_def_to_spec(bad)


def test_registered_tools_scope_is_clean() -> None:
    td = _search_tool()
    assert not TOOLS.contains("web-search")
    with registered_tools([td]):
        assert TOOLS.contains("web-search")
    assert not TOOLS.contains("web-search")  # cleaned up


def test_registered_tools_cleans_up_on_error() -> None:
    td = _search_tool()
    with pytest.raises(ToolDefError):
        with registered_tools([td, td]):  # duplicate id mid-block
            pass
    assert not TOOLS.contains("web-search")


def test_validate_tool_def_echoes_schema() -> None:
    out = validate_tool_def(_search_tool())
    assert out["ok"] is True
    assert "query" in out["arg_schema"]["properties"]
    assert out["return_schema"] is not None


def test_validate_tool_def_reports_error() -> None:
    out = validate_tool_def(ToolDef(id="Bad Id"))
    assert out["ok"] is False
    assert "error" in out


def _tool_granting_graph() -> Graph:
    node = GraphNode.model_validate(
        {"id": "searcher", "description": "search", "tools": {"tool_grants": ["web-search"]}}
    )
    g = resolve(Graph(nodes=[node], tool_defs=[_search_tool()]))
    # resolve drops tool_defs? No — it deep-copies the whole graph.
    return g


def test_preview_grants_authored_tool() -> None:
    g = _tool_granting_graph()
    result = preview_agent(g.nodes[0], g.tool_defs)
    assert result.ok, result.error
    assert result.agent is not None
    assert result.agent["tools"]["tool_grants"] == ["web-search"]


def test_preview_without_tool_def_fails_grant() -> None:
    g = _tool_granting_graph()
    result = preview_agent(g.nodes[0], tool_defs=[])  # tool not registered
    assert not result.ok
    assert "tool_grants" in (result.error or "")


def test_dry_run_uses_graph_tool_defs() -> None:
    g = _tool_granting_graph()
    result = dry_run(g)
    assert result.ok, [n.error for n in result.nodes]


def test_export_writes_tools_stub_and_imports(tmp_path: Path) -> None:
    g = _tool_granting_graph()
    dest = tmp_path / "pkg"
    result = export_graph(g, str(dest))
    assert "_tools.py" in result.files

    # The exported package imports with only the framework, registering the tool
    # before the agent loader validates its grant.
    code = (
        "import importlib.util, sys;"
        f"spec=importlib.util.spec_from_file_location('expkg', r'{dest / '__init__.py'}');"
        "m=importlib.util.module_from_spec(spec); sys.modules['expkg']=m;"
        "spec.loader.exec_module(m);"
        "print(m.searcher.tools.tool_grants)"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "web-search" in proc.stdout


def test_exported_tool_stub_raises(tmp_path: Path) -> None:
    g = _tool_granting_graph()
    dest = tmp_path / "pkg"
    export_graph(g, str(dest))
    spec = importlib.util.spec_from_file_location("extools", dest / "_tools.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tool = TOOLS.get("web-search")
    try:
        with pytest.raises(NotImplementedError):
            tool.callable(query="x")
    finally:
        TOOLS.clear()
