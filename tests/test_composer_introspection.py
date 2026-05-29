"""Tests for the introspection layer (node-types + catalogs)."""

from __future__ import annotations

from composer.introspection import catalog_payload, node_type_schemas


def test_node_type_schemas_cover_all_layers() -> None:
    schemas = node_type_schemas()
    assert set(schemas) == {
        "identity",
        "model",
        "io",
        "tools",
        "policy",
        "errors",
        "telemetry",
    }
    # Each is a real JSON Schema object.
    assert "properties" in schemas["policy"]
    assert "max_steps" in schemas["policy"]["properties"]


def test_catalog_payload_is_json_safe() -> None:
    import json

    payload = catalog_payload()
    json.dumps(payload)  # would raise if any value were unserialisable
    assert {m["id"] for m in payload["models"]} >= {"test:echo"}
    assert {t["id"] for t in payload["io_types"]} >= {"text", "json"}
    assert {e["id"] for e in payload["errors"]} >= {"tool_failure"}
    assert {s["id"] for s in payload["sinks"]} >= {"console", "noop"}


def test_tool_catalog_serialises_arg_schema(echo_tool: str) -> None:
    payload = catalog_payload()
    tool = next(t for t in payload["tools"] if t["id"] == echo_tool)
    assert "properties" in tool["arg_schema"]
