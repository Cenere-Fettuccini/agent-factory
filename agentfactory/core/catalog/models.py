"""Core model catalog.

Defines the sealed set of Claude models shipped with the framework, plus the
``ModelDescriptor`` component type used by the model layer. Custom models
(open-weights, third-party endpoints, fine-tunes) live as extension entries
and are added through ``MODEL_REGISTRY.register(...)``.

The :class:`CoreModel` enum gives static type checkers the exact set of valid
core model keys — agents that hardcode against the enum get compile-time
verification, while config-driven agents fall through to the runtime registry.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from agentfactory.core.registry import Registry


class CoreModel(StrEnum):
    """Sealed enumeration of framework-shipped Claude models.

    Values are the exact model IDs accepted by the Anthropic API. Using the
    enum (rather than a string literal) gives mypy/pyright a closed set to
    check against; downstream layers that accept ``CoreModel | str`` allow
    extension models too.
    """

    OPUS_4_7 = "claude-opus-4-7"
    SONNET_4_6 = "claude-sonnet-4-6"
    HAIKU_4_5 = "claude-haiku-4-5-20251001"


# Cost/capability tier — used by routing policies (e.g. "downshift to a
# cheaper tier when input is below N tokens"). Ordered low → high.
ModelTier = Literal["haiku", "sonnet", "opus"]


class ModelDescriptor(BaseModel):
    """A model-layer component describing one selectable model.

    A descriptor is not the model itself; it is the *catalog entry* that the
    model layer references by key. The actual API call is performed by the
    executor at runtime using the fields here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Required by the Component protocol.
    kind: Literal["model"] = "model"
    key: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Registry key. For core models this equals the API model ID.",
    )

    # Model-specific metadata.
    api_id: str = Field(
        ...,
        description="The exact identifier passed to the Anthropic SDK.",
    )
    tier: ModelTier = Field(
        ...,
        description="Cost/capability tier for routing decisions.",
    )
    max_context_tokens: PositiveInt = Field(
        ...,
        description="Provider-declared max context window.",
    )
    supports_vision: bool = False
    supports_tools: bool = True
    supports_prompt_cache: bool = True
    description: str = Field(
        default="",
        max_length=512,
        description="Short human-readable note.",
    )


# Process-wide registry singleton for model components.
MODEL_REGISTRY: Final[Registry[ModelDescriptor]] = Registry(
    kind="model", component_type=ModelDescriptor
)


def _bootstrap_core() -> None:
    """Populate and seal the core model tier. Called once at import time."""
    core_entries: tuple[ModelDescriptor, ...] = (
        ModelDescriptor(
            key=CoreModel.OPUS_4_7.value,
            api_id=CoreModel.OPUS_4_7.value,
            tier="opus",
            max_context_tokens=200_000,
            supports_vision=True,
            description="Most capable Claude model. Default for hard reasoning.",
        ),
        ModelDescriptor(
            key=CoreModel.SONNET_4_6.value,
            api_id=CoreModel.SONNET_4_6.value,
            tier="sonnet",
            max_context_tokens=200_000,
            supports_vision=True,
            description="Balanced capability/cost. Default for general agents.",
        ),
        ModelDescriptor(
            key=CoreModel.HAIKU_4_5.value,
            api_id=CoreModel.HAIKU_4_5.value,
            tier="haiku",
            max_context_tokens=200_000,
            supports_vision=True,
            description="Fastest and cheapest Claude. Default for narrow tasks.",
        ),
    )
    for entry in core_entries:
        MODEL_REGISTRY._register_core(entry)
    MODEL_REGISTRY.seal_core()


_bootstrap_core()
