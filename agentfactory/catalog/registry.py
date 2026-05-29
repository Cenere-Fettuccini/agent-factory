"""A typed, in-memory registry keyed by string id."""

from __future__ import annotations

from typing import Generic, TypeVar

from agentfactory.base import AgentFactoryError

T = TypeVar("T")


class UnknownCatalogEntry(AgentFactoryError):
    """Raised when a catalog lookup misses."""


class DuplicateCatalogEntry(AgentFactoryError):
    """Raised when registering an id that already exists."""


class Registry(Generic[T]):
    """A string-keyed registry of catalog specs."""

    def __init__(self, label: str = "entry") -> None:
        self._label = label
        self._items: dict[str, T] = {}

    def register(self, id: str, spec: T, *, overwrite: bool = False) -> T:
        if id in self._items and not overwrite:
            raise DuplicateCatalogEntry(
                f"{self._label} {id!r} is already registered"
            )
        self._items[id] = spec
        return spec

    def get(self, id: str) -> T:
        try:
            return self._items[id]
        except KeyError:
            raise UnknownCatalogEntry(
                f"unknown {self._label} {id!r}; known: {sorted(self._items)}"
            ) from None

    def contains(self, id: str) -> bool:
        return id in self._items

    def ids(self) -> list[str]:
        return list(self._items)

    def clear(self) -> None:
        self._items.clear()
