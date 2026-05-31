"""Tests for export: folder layout, round-trip import, dangerous-path refusal."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from composer.export import ExportError, export_graph
from composer.resolver import resolve
from composer.schemas.graph import Graph


def _resolved(data: dict[str, Any]) -> Graph:
    return resolve(Graph.model_validate(data))


def test_export_writes_expected_files(tmp_path: Path) -> None:
    g = _resolved({"nodes": [{"id": "my-agent", "description": "summarise"}]})
    dest = tmp_path / "pkg"
    result = export_graph(g, str(dest))
    # _runtime.py is always emitted (it hosts the entrypoint runners), even for
    # an edgeless graph with no subagent tools to register.
    assert set(result.files) == {
        "__init__.py",
        "_graph.json",
        "_runtime.py",
        "my_agent.json",
        "my_agent.py",
    }
    assert result.agent_ids == ["my-agent"]


def test_export_uses_tool_node_as_provider_not_agent(tmp_path: Path) -> None:
    g = _resolved(
        {
            "nodes": [{"id": "searcher"}, {"id": "toolbox", "kind": "tool"}],
            "edges": [{"source": "searcher", "target": "toolbox"}],
            "tool_defs": [
                {
                    "id": "web-search",
                    "node_id": "toolbox",
                    "args": {"query": {"type_key": "text"}},
                }
            ],
        }
    )
    dest = tmp_path / "pkg"
    result = export_graph(g, str(dest))
    assert "searcher.py" in result.files
    assert "toolbox.py" not in result.files
    assert "_tools.py" in result.files
    assert result.agent_ids == ["searcher"]


def test_export_writes_runtime_for_internal_agent_edges(tmp_path: Path) -> None:
    g = Graph.model_validate(
        {
            "layers": ["top", "workers"],
            "nodes": [
                {
                    "id": "top-agent",
                    "layer": "top",
                    "trigger": "user_query",
                    "model": {"model_id": "test:echo"},
                },
                {
                    "id": "worker",
                    "layer": "workers",
                    "model": {"model_id": "test:echo"},
                },
            ],
            "edges": [{"source": "top-agent", "target": "worker"}],
        }
    )
    dest = tmp_path / "pkg"
    result = export_graph(g, str(dest))

    assert "_runtime.py" in result.files
    assert "top_agent.py" in result.files
    assert "worker.py" in result.files

    spec = importlib.util.spec_from_file_location("netpkg", dest / "__init__.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["netpkg"] = module
    spec.loader.exec_module(module)

    assert hasattr(module, "run_top_agent_sync")
    assert "agentfactory.subagent.worker" in module.top_agent.tools.tool_grants
    out = module.run_top_agent_sync({"input": "hello"})
    assert isinstance(out, dict)


def test_edgeless_export_entrypoint_runs(tmp_path: Path) -> None:
    # A single agent with no call edges still gets a working entrypoint: _runtime
    # is always written and imported, so calling it does not NameError.
    g = Graph.model_validate(
        {
            "layers": ["solo"],
            "nodes": [
                {
                    "id": "solo",
                    "layer": "solo",
                    "trigger": "user_query",
                    "model": {"model_id": "test:echo"},
                }
            ],
            "edges": [],
        }
    )
    dest = tmp_path / "pkg"
    result = export_graph(g, str(dest))
    assert "_runtime.py" in result.files

    spec = importlib.util.spec_from_file_location("solopkg", dest / "__init__.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["solopkg"] = module
    spec.loader.exec_module(module)
    out = module.run_solo_sync({"input": "hi"})
    assert isinstance(out, dict)


def test_broken_python_import_defers_to_call_time(tmp_path: Path) -> None:
    # A python_import binding to a missing module must not break the whole
    # package import — the failure surfaces only when that tool is called.
    g = Graph.model_validate(
        {
            "layers": ["top", "tools"],
            "nodes": [
                {
                    "id": "caller",
                    "layer": "top",
                    "trigger": "user_query",
                    "model": {"model_id": "test:echo"},
                },
                {"id": "box", "kind": "tool", "layer": "tools"},
            ],
            "edges": [{"source": "caller", "target": "box"}],
            "tool_defs": [
                {
                    "id": "broken",
                    "node_id": "box",
                    "binding": {
                        "kind": "python_import",
                        "module": "nonexistent.module.xyz",
                        "callable": "nope",
                    },
                    "args": {"x": {"type_key": "text"}},
                }
            ],
        }
    )
    dest = tmp_path / "pkg"
    export_graph(resolve(g), str(dest))

    spec = importlib.util.spec_from_file_location("brokenpkg", dest / "__init__.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["brokenpkg"] = module
    spec.loader.exec_module(module)  # must not raise despite the bad binding

    from agentfactory.catalog.tools import TOOLS

    with pytest.raises(RuntimeError, match="not callable"):
        TOOLS.get("broken").callable(x="hi")


def test_export_groups_modules_into_subpackages(tmp_path: Path) -> None:
    g = _resolved(
        {
            "nodes": [
                {"id": "idea-lead", "description": "ideate", "module": "Ideation"},
                {
                    "id": "paper-scout",
                    "description": "collect papers",
                    "module": "paper collection",
                },
            ]
        }
    )
    dest = tmp_path / "pkg"
    result = export_graph(g, str(dest))

    assert "ideation/idea_lead.py" in result.files
    assert "ideation/idea_lead.json" in result.files
    assert "ideation/__init__.py" in result.files
    assert "paper_collection/paper_scout.py" in result.files
    assert "paper_collection/paper_scout.json" in result.files
    assert "paper_collection/__init__.py" in result.files

    spec = importlib.util.spec_from_file_location("expkg", dest / "__init__.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["expkg"] = module
    spec.loader.exec_module(module)
    assert module.idea_lead.identity.id == "idea-lead"
    assert module.paper_scout.identity.id == "paper-scout"


def test_exported_package_imports_with_only_framework(tmp_path: Path) -> None:
    g = _resolved({"nodes": [{"id": "loader-test", "description": "do work"}]})
    dest = tmp_path / "pkg"
    export_graph(g, str(dest))

    # Import in a clean subprocess to prove no dependency on composer/.
    code = (
        "import importlib.util, sys;"
        f"spec=importlib.util.spec_from_file_location('expkg', r'{dest / '__init__.py'}');"
        "m=importlib.util.module_from_spec(spec); sys.modules['expkg']=m;"
        "spec.loader.exec_module(m);"
        "print(m.loader_test.identity.id)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert "loader-test" in proc.stdout


def test_loader_round_trips_agent(tmp_path: Path) -> None:
    g = _resolved({"nodes": [{"id": "rt", "description": "x"}]})
    dest = tmp_path / "pkg"
    export_graph(g, str(dest))
    spec = importlib.util.spec_from_file_location("rt_mod", dest / "rt.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.agent.identity.id == "rt"


def test_refuses_root_destination() -> None:
    g = _resolved({"nodes": [{"id": "a", "description": "x"}]})
    root = Path(sys.executable).anchor or "/"
    with pytest.raises(ExportError, match="root"):
        export_graph(g, root)


def test_refuses_empty_destination() -> None:
    g = _resolved({"nodes": [{"id": "a", "description": "x"}]})
    with pytest.raises(ExportError, match="empty"):
        export_graph(g, "  ")


def test_refuses_nonempty_dir_without_overwrite(tmp_path: Path) -> None:
    g = _resolved({"nodes": [{"id": "a", "description": "x"}]})
    (tmp_path / "existing.txt").write_text("hi", encoding="utf-8")
    with pytest.raises(ExportError, match="not empty"):
        export_graph(g, str(tmp_path))
    # overwrite=True proceeds.
    result = export_graph(g, str(tmp_path), overwrite=True)
    assert "__init__.py" in result.files


def test_invalid_node_aborts_before_writing(tmp_path: Path) -> None:
    g = Graph.model_validate(
        {
            "nodes": [
                {
                    "id": "bad",
                    "model": {"model_id": "nope:nope"},
                    "io": {
                        "input_schema": {"name": "I", "fields": {"q": {"type_key": "text"}}},
                        "output_schema": {"name": "O", "fields": {"a": {"type_key": "text"}}},
                    },
                }
            ]
        }
    )
    dest = tmp_path / "pkg"
    with pytest.raises(ExportError, match="invalid"):
        export_graph(g, str(dest))
    assert not dest.exists()  # nothing written
