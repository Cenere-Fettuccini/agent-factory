"""End-to-end HTTP tests: drive the whole authoring flow over the API."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from composer import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_node_types_and_catalogs(client: TestClient) -> None:
    assert "policy" in client.get("/node-types").json()
    cats = client.get("/catalogs").json()
    assert {m["id"] for m in cats["models"]} >= {"test:echo"}


def test_graph_validate_endpoint(client: TestClient) -> None:
    body = {"nodes": [{"id": "a"}], "edges": [{"source": "a", "target": "ghost"}]}
    result = client.post("/graph/validate", json=body).json()
    assert result["valid"] is False
    assert any(i["code"] == "dangling_edge" for i in result["issues"])


def test_resolve_endpoint(client: TestClient) -> None:
    body = {"nodes": [{"id": "p", "description": "plan and reason"}]}
    result = client.post("/presets/resolve", json=body).json()
    assert result["nodes"][0]["model"]["model_id"] == "anthropic:claude-opus-4-7"


def test_preview_endpoint(client: TestClient) -> None:
    node = {"id": "pv", "description": "summarise"}
    resolved = client.post("/presets/resolve", json={"nodes": [node]}).json()
    result = client.post(
        "/agents/preview", json={"node": resolved["nodes"][0]}
    ).json()
    assert result["ok"] is True
    assert result["agent"]["identity"]["id"] == "pv"


def test_full_flow_to_export(client: TestClient, tmp_path: Path) -> None:
    """Resolve -> dry-run -> export, exactly as a curl-driven client would."""
    graph = {
        "nodes": [
            {"id": "planner", "description": "plan and reason"},
            {"id": "worker", "description": "quickly classify input"},
        ],
        "edges": [{"source": "planner", "target": "worker"}],
    }
    resolved = client.post("/presets/resolve", json=graph).json()
    dry = client.post("/export/dry-run", json=resolved).json()
    assert dry["ok"] is True

    dest = tmp_path / "out"
    export = client.post(
        "/export", json={"graph": resolved, "destination": str(dest)}
    )
    assert export.status_code == 200
    assert set(export.json()["agent_ids"]) == {"planner", "worker"}
    assert (dest / "__init__.py").exists()


def test_export_rejects_root_path(client: TestClient) -> None:
    import sys

    root = Path(sys.executable).anchor or "/"
    body = {
        "graph": {"nodes": [{"id": "a", "description": "x"}]},
        "destination": root,
    }
    resp = client.post("/export", json=body)
    assert resp.status_code == 400
    assert "root" in resp.json()["detail"]
