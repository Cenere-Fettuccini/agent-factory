"""Tests for ToolsLayer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentfactory.layers.tools import ToolsLayer


def test_empty_default() -> None:
    layer = ToolsLayer()
    assert layer.tool_grants == []
    assert layer.caller_allowlist == []


def test_ungranted_tool_rejected() -> None:
    with pytest.raises(ValidationError, match="tool catalog"):
        ToolsLayer(tool_grants=["does_not_exist"])


def test_granted_tool_accepted(echo_tool: str) -> None:
    layer = ToolsLayer(tool_grants=[echo_tool])
    assert layer.tool_grants == ["echo"]


def test_caller_allowlist_stored() -> None:
    layer = ToolsLayer(caller_allowlist=["other-agent"])
    assert layer.caller_allowlist == ["other-agent"]
