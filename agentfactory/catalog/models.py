"""Catalog of model specs and compilation into PydanticAI model objects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from agentfactory.catalog.registry import Registry

if TYPE_CHECKING:
    from pydantic_ai.models import Model

Provider = Literal["anthropic", "openai", "test"]


class ModelSpec(BaseModel):
    """A catalogued model: provider, underlying id, and capabilities."""

    model_config = ConfigDict(frozen=True)

    id: str
    provider: Provider
    provider_model_id: str
    context_window: int
    supports_tools: bool


MODELS: Registry[ModelSpec] = Registry("model")


def seed_defaults() -> None:
    if MODELS.ids():
        return
    MODELS.register(
        "anthropic:claude-opus-4-7",
        ModelSpec(
            id="anthropic:claude-opus-4-7",
            provider="anthropic",
            provider_model_id="claude-opus-4-7",
            context_window=200_000,
            supports_tools=True,
        ),
    )
    MODELS.register(
        "anthropic:claude-sonnet-4-6",
        ModelSpec(
            id="anthropic:claude-sonnet-4-6",
            provider="anthropic",
            provider_model_id="claude-sonnet-4-6",
            context_window=200_000,
            supports_tools=True,
        ),
    )
    MODELS.register(
        "anthropic:claude-haiku-4-5",
        ModelSpec(
            id="anthropic:claude-haiku-4-5",
            provider="anthropic",
            provider_model_id="claude-haiku-4-5",
            context_window=200_000,
            supports_tools=True,
        ),
    )
    MODELS.register(
        "test:echo",
        ModelSpec(
            id="test:echo",
            provider="test",
            provider_model_id="echo",
            context_window=100_000,
            supports_tools=True,
        ),
    )


def build_pydantic_ai_model(spec: ModelSpec) -> Model:
    """Compile a ModelSpec into a concrete PydanticAI Model. Switch on provider."""
    if spec.provider == "test":
        from pydantic_ai.models.test import TestModel

        return TestModel()
    if spec.provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel

        return AnthropicModel(spec.provider_model_id)
    if spec.provider == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel

        return OpenAIChatModel(spec.provider_model_id)
    raise ValueError(f"unsupported provider {spec.provider!r}")
