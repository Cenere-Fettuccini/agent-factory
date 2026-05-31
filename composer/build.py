"""Turn a GraphNode into a real framework Agent.

This is the single place a node becomes an Agent. Preview, dry-run, and export
all go through here, so they validate identically — we never reimplement the
framework's rules in the API layer.
"""

from __future__ import annotations

from agentfactory.agent import Agent
from agentfactory.base import Identity
from agentfactory.layers.errors import ErrorLayer
from agentfactory.layers.io import IOLayer
from agentfactory.layers.model import ModelLayer
from agentfactory.layers.policy import PolicyLayer
from agentfactory.layers.telemetry import TelemetryLayer
from agentfactory.layers.tools import ToolsLayer
from composer.schemas.graph import GraphNode


class NodeBuildError(Exception):
    """Raised when a node cannot be turned into a valid Agent."""

    def __init__(self, node_id: str, message: str) -> None:
        self.node_id = node_id
        super().__init__(message)


def node_to_agent(node: GraphNode) -> Agent:
    """Build a frozen Agent from a node, surfacing the framework's own errors.

    ``model`` and ``io`` are required to build; everything else defaults.
    """
    if node.kind != "agent":
        raise NodeBuildError(node.id, f"node kind {node.kind!r} is not an agent")
    if node.model is None:
        raise NodeBuildError(node.id, "node has no model layer; resolve or set it first")
    if node.io is None:
        raise NodeBuildError(node.id, "node has no io layer; resolve or set it first")

    try:
        identity = Identity(
            id=node.id,
            name=node.name or node.id,
            version=node.version,
            description=node.description,
            tags=node.tags,
        )
        return Agent(
            identity=identity,
            model=ModelLayer.model_validate(node.model),
            io=IOLayer.model_validate(node.io),
            tools=(
                ToolsLayer.model_validate(node.tools)
                if node.tools is not None
                else ToolsLayer()
            ),
            policy=(
                PolicyLayer.model_validate(node.policy)
                if node.policy is not None
                else PolicyLayer()
            ),
            errors=(
                ErrorLayer.model_validate(node.errors)
                if node.errors is not None
                else ErrorLayer()
            ),
            telemetry=(
                TelemetryLayer.model_validate(node.telemetry)
                if node.telemetry is not None
                else TelemetryLayer()
            ),
        )
    except NodeBuildError:
        raise
    except Exception as exc:  # noqa: BLE001 — translate framework errors to ours
        raise NodeBuildError(node.id, str(exc)) from exc
