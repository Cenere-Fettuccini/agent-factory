"""Tests for the dual-tier Registry."""

from __future__ import annotations

import pytest

from agentfactory.core.catalog.models import MODEL_REGISTRY, ModelDescriptor
from agentfactory.core.registry import Registry, RegistryError


@pytest.fixture(autouse=True)
def _cleanup_extensions():
    """Remove any extension entries the test left behind."""
    before = set(MODEL_REGISTRY.extension_keys())
    yield
    for key in MODEL_REGISTRY.extension_keys():
        if key not in before:
            MODEL_REGISTRY.unregister(key)


def _ext(key: str = "ext-model") -> ModelDescriptor:
    return ModelDescriptor(
        key=key, api_id=key, tier="sonnet", max_context_tokens=8000,
        description="test extension",
    )


def test_core_is_sealed_at_import() -> None:
    assert MODEL_REGISTRY.core_sealed is True


def test_core_keys_present() -> None:
    keys = MODEL_REGISTRY.core_keys()
    assert "claude-opus-4-7" in keys
    assert "claude-sonnet-4-6" in keys
    assert "claude-haiku-4-5-20251001" in keys


def test_register_extension_then_lookup() -> None:
    MODEL_REGISTRY.register(_ext("ext-a"))
    assert MODEL_REGISTRY.has("ext-a")
    assert MODEL_REGISTRY.get("ext-a").api_id == "ext-a"


def test_extension_cannot_shadow_core() -> None:
    with pytest.raises(RegistryError, match="core component"):
        MODEL_REGISTRY.register(
            ModelDescriptor(
                key="claude-opus-4-7", api_id="hijack",
                tier="opus", max_context_tokens=1000,
            )
        )


def test_duplicate_extension_requires_override() -> None:
    MODEL_REGISTRY.register(_ext("ext-dup"))
    with pytest.raises(RegistryError, match="already registered"):
        MODEL_REGISTRY.register(_ext("ext-dup"))
    # Override should succeed.
    MODEL_REGISTRY.register(_ext("ext-dup"), override=True)


def test_core_cannot_be_unregistered() -> None:
    with pytest.raises(RegistryError, match="core component"):
        MODEL_REGISTRY.unregister("claude-opus-4-7")


def test_lookup_missing_raises() -> None:
    with pytest.raises(RegistryError, match="no component"):
        MODEL_REGISTRY.get("never-registered")


def test_kind_mismatch_rejected() -> None:
    reg: Registry[ModelDescriptor] = Registry(
        kind="model", component_type=ModelDescriptor
    )
    # Manually craft a descriptor with the wrong kind via the model_construct
    # bypass (Pydantic allows this for the test).
    bad = ModelDescriptor.model_construct(
        kind="tool",  # type: ignore[arg-type]
        key="x", api_id="x", tier="sonnet", max_context_tokens=1000,
    )
    with pytest.raises(RegistryError, match="declares kind"):
        reg._register_core(bad)


def test_seal_is_idempotent() -> None:
    MODEL_REGISTRY.seal_core()
    MODEL_REGISTRY.seal_core()
    assert MODEL_REGISTRY.core_sealed
