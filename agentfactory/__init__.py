"""AgentFactory — a typed, layered framework for well-bounded agents."""

from __future__ import annotations

from agentfactory import catalog as _catalog
from agentfactory.agent import Agent
from agentfactory.base import AgentFactoryError
from agentfactory.builder import AgentBuilder

# Seed every catalog with its defaults on import so construction-time
# validation has something to check against.
_catalog.seed_defaults()

__all__ = ["Agent", "AgentBuilder", "AgentFactoryError"]
