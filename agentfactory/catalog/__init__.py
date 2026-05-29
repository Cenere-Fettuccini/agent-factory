"""Catalogs: authoritative registries for everything an agent can name."""

from __future__ import annotations

from agentfactory.catalog import errors, io_types, models, sinks, tools


def seed_defaults() -> None:
    """Seed every catalog with its default entries. Idempotent."""
    models.seed_defaults()
    io_types.seed_defaults()
    tools.seed_defaults()
    errors.seed_defaults()
    sinks.seed_defaults()


__all__ = ["errors", "io_types", "models", "seed_defaults", "sinks", "tools"]
