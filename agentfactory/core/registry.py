"""Component registries — the dual-catalog (sealed core + open extensions).

Every layer's catalog is exposed through a :class:`Registry` instance. The
registry holds two tiers:

* **Core**: components shipped with the framework. Populated once at module
  import and then sealed — :meth:`Registry.seal_core` flips a one-way flag
  that bans further core writes for the process lifetime.
* **Extensions**: user-registered components added via :meth:`Registry.register`.
  Extensions can be added at any time before the registry is fully frozen.

Lookup precedence is **core → extensions → raise**. Name collisions are
rejected at registration time:

* Registering an extension whose name exists in core raises immediately.
* Registering an extension whose name exists in extensions raises unless
  ``override=True`` is passed.

Once an agent class is finalized, the builder snapshots the components it
referenced; later registry mutations cannot affect already-built agents.
"""

from __future__ import annotations

from threading import RLock
from typing import Generic, TypeVar

from agentfactory.core.protocols import COMPONENT_KINDS, Component

T = TypeVar("T", bound=Component)


class RegistryError(Exception):
    """Raised for any registry-related violation: sealed writes, duplicates,
    kind mismatches, unknown lookups."""


class Registry(Generic[T]):
    """Type-parameterized component registry.

    One instance per component kind. The instance is the source of truth for
    that kind's catalog across the whole process.
    """

    def __init__(self, kind: str, component_type: type[T]) -> None:
        if kind not in COMPONENT_KINDS:
            raise RegistryError(
                f"unknown component kind {kind!r}; "
                f"valid kinds are {sorted(COMPONENT_KINDS)}"
            )
        self._kind: str = kind
        self._component_type: type[T] = component_type
        self._core: dict[str, T] = {}
        self._ext: dict[str, T] = {}
        self._core_sealed: bool = False
        self._lock: RLock = RLock()

    # --- core-tier writes (framework-internal) ------------------------------

    def _register_core(self, component: T) -> None:
        """Framework-internal: add a component to the sealed core tier.

        Public code must not call this. Core catalog modules call it during
        their import-time bootstrap, then call :meth:`seal_core`.
        """
        with self._lock:
            if self._core_sealed:
                raise RegistryError(
                    f"core catalog for kind={self._kind!r} is already sealed"
                )
            self._validate_component(component)
            if component.key in self._core:
                raise RegistryError(
                    f"core component {component.key!r} already registered "
                    f"for kind={self._kind!r}"
                )
            self._core[component.key] = component

    def seal_core(self) -> None:
        """Lock the core tier. Idempotent. Cannot be undone for the process."""
        with self._lock:
            self._core_sealed = True

    @property
    def core_sealed(self) -> bool:
        return self._core_sealed

    # --- extension-tier writes (public API) ---------------------------------

    def register(self, component: T, *, override: bool = False) -> T:
        """Register a user-supplied component into the extension tier.

        Raises :class:`RegistryError` if:

        * the component's ``kind`` does not match this registry,
        * the component is not an instance of the declared component type,
        * the name collides with a core component (always — core is sacred),
        * the name collides with an existing extension and ``override`` is False.
        """
        with self._lock:
            self._validate_component(component)
            if component.key in self._core:
                raise RegistryError(
                    f"{component.key!r} is a core component for "
                    f"kind={self._kind!r}; core names cannot be overridden"
                )
            if component.key in self._ext and not override:
                raise RegistryError(
                    f"extension component {component.key!r} already registered "
                    f"for kind={self._kind!r}; pass override=True to replace"
                )
            self._ext[component.key] = component
            return component

    def unregister(self, key: str) -> None:
        """Remove an extension component. Core components cannot be unregistered."""
        with self._lock:
            if key in self._core:
                raise RegistryError(
                    f"{key!r} is a core component; cannot unregister"
                )
            if key not in self._ext:
                raise RegistryError(
                    f"no extension component {key!r} registered for "
                    f"kind={self._kind!r}"
                )
            del self._ext[key]

    # --- lookup -------------------------------------------------------------

    def get(self, key: str) -> T:
        """Resolve a component by key. Core wins over extensions."""
        with self._lock:
            if key in self._core:
                return self._core[key]
            if key in self._ext:
                return self._ext[key]
            raise RegistryError(
                f"no component {key!r} registered for kind={self._kind!r}"
            )

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._core or key in self._ext

    def keys(self) -> tuple[str, ...]:
        """All known keys (core first, then extensions), sorted within each tier."""
        with self._lock:
            return tuple(sorted(self._core)) + tuple(sorted(self._ext))

    def core_keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._core))

    def extension_keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._ext))

    # --- internals ----------------------------------------------------------

    def _validate_component(self, component: T) -> None:
        if not isinstance(component, self._component_type):
            raise RegistryError(
                f"component {component!r} is not an instance of "
                f"{self._component_type.__name__}"
            )
        # Belt-and-suspenders: components carry their own `kind`; reject if
        # someone hand-rolled a component with the wrong discriminator.
        declared = getattr(component, "kind", None)
        if declared != self._kind:
            raise RegistryError(
                f"component {component!r} declares kind={declared!r} but "
                f"was registered into a kind={self._kind!r} registry"
            )

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.has(key)

    def __len__(self) -> int:
        with self._lock:
            return len(self._core) + len(self._ext)

    def __repr__(self) -> str:
        return (
            f"Registry(kind={self._kind!r}, "
            f"core={len(self._core)}, ext={len(self._ext)}, "
            f"sealed={self._core_sealed})"
        )


# Note: the actual per-kind registry singletons (MODEL_REGISTRY, TOOL_REGISTRY,
# etc.) live in their respective catalog modules. That keeps the import graph
# acyclic: registry.py stays leaf-level; catalogs depend on it, layers depend
# on catalogs.
