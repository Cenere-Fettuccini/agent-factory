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
    assert set(result.files) == {
        "__init__.py",
        "_graph.json",
        "my_agent.json",
        "my_agent.py",
    }
    assert result.agent_ids == ["my-agent"]


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
