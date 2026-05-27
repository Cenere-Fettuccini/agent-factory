"""Core component catalogs. Importing this package bootstraps the sealed
core tier of every registry. Once imported, the core tiers are frozen.
"""

from agentfactory.core.catalog.models import (
    MODEL_REGISTRY,
    CoreModel,
    ModelDescriptor,
)

__all__ = ["MODEL_REGISTRY", "CoreModel", "ModelDescriptor"]
