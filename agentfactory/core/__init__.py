"""Core building blocks: the inheritance chain, protocols, and registries."""

from agentfactory.core.base import BaseAgent
from agentfactory.core.registry import Registry, RegistryError

__all__ = ["BaseAgent", "Registry", "RegistryError"]
