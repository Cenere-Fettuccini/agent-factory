"""Tests for the typed Registry."""

from __future__ import annotations

import pytest

from agentfactory.catalog.registry import (
    DuplicateCatalogEntry,
    Registry,
    UnknownCatalogEntry,
)


def test_register_and_get() -> None:
    reg: Registry[int] = Registry("thing")
    reg.register("a", 1)
    assert reg.get("a") == 1
    assert reg.contains("a")
    assert reg.ids() == ["a"]


def test_get_missing_raises() -> None:
    reg: Registry[int] = Registry("thing")
    with pytest.raises(UnknownCatalogEntry):
        reg.get("nope")


def test_duplicate_raises_unless_overwrite() -> None:
    reg: Registry[int] = Registry("thing")
    reg.register("a", 1)
    with pytest.raises(DuplicateCatalogEntry):
        reg.register("a", 2)
    reg.register("a", 2, overwrite=True)
    assert reg.get("a") == 2


def test_clear() -> None:
    reg: Registry[int] = Registry("thing")
    reg.register("a", 1)
    reg.clear()
    assert not reg.contains("a")
    assert reg.ids() == []
