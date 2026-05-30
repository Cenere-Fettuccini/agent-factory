"""Materialise UI-authored tools into real framework ``ToolSpec``s.

The framework's tool catalog is code-registered and every ``ToolSpec`` needs a
real ``callable`` (``agentfactory/catalog/tools.py``). A tool authored in the UI
has no implementation, so we:

* build a faithful ``arg_schema``/``return_schema`` from the IO type lexicon
  (the same vocabulary IO layers use), and
* attach a **stub callable** that raises ``NotImplementedError``.

Authored tools are carried in the request graph (``Graph.tool_defs``) and
registered *transiently* via :func:`registered_tools` for the duration of a
build/preview/dry-run, so the global catalog is never permanently mutated and
the server stays stateless. On export they are written as a typed stub module
the user fills in (:func:`render_tools_module`).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel, create_model

from agentfactory.catalog.io_types import IO_TYPES
from agentfactory.catalog.tools import TOOLS, ToolSpec
from composer.schemas.graph import ToolDef, ToolDefField

_TOOL_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class ToolDefError(Exception):
    """Raised when an authored tool definition cannot be materialised."""


def _check_id(tool_id: str) -> None:
    if not _TOOL_ID_RE.match(tool_id):
        raise ToolDefError(
            f"tool id {tool_id!r} must match {_TOOL_ID_RE.pattern!r} "
            "(lowercase, start with a letter, alnum/underscore/hyphen)"
        )


def _build_model(name: str, fields: dict[str, ToolDefField]) -> type[BaseModel]:
    """Build a Pydantic model from lexicon-typed fields (mirrors IOSchema)."""
    definitions: dict[str, Any] = {}
    for field_name, spec in fields.items():
        if not IO_TYPES.contains(spec.type_key):
            raise ToolDefError(
                f"field {field_name!r} uses type_key {spec.type_key!r} which is "
                f"not in the IO type lexicon; known: {IO_TYPES.ids()}"
            )
        py_type = IO_TYPES.get(spec.type_key).python_type
        if spec.required:
            definitions[field_name] = (py_type, ...)
        else:
            definitions[field_name] = (py_type | None, None)
    return create_model(name, **definitions)


def _stub_callable(tool_id: str) -> Callable[..., Any]:
    def _impl(**kwargs: Any) -> Any:
        raise NotImplementedError(
            f"tool {tool_id!r} needs an implementation; fill in this callable"
        )

    _impl.__name__ = f"{tool_id.replace('-', '_')}_impl"
    return _impl


def _model_name(tool_id: str, suffix: str) -> str:
    parts = re.split(r"[-_]", tool_id)
    return "".join(p.capitalize() for p in parts if p) + suffix


def tool_def_to_spec(td: ToolDef) -> ToolSpec:
    """Turn an authored ``ToolDef`` into a real (stub-backed) ``ToolSpec``."""
    _check_id(td.id)
    arg_schema = _build_model(_model_name(td.id, "Args"), td.args)
    return_schema = (
        _build_model(_model_name(td.id, "Result"), td.returns)
        if td.returns is not None
        else None
    )
    return ToolSpec(
        id=td.id,
        description=td.description,
        arg_schema=arg_schema,
        return_schema=return_schema,
        callable=_stub_callable(td.id),
    )


@contextmanager
def registered_tools(tool_defs: Iterable[ToolDef]) -> Iterator[None]:
    """Register authored tools into the global catalog for the block's duration.

    Cleans up afterwards even on error, removing only the ids we added, so the
    process-global catalog is left exactly as we found it.
    """
    added: list[str] = []
    try:
        for td in tool_defs:
            if TOOLS.contains(td.id):
                raise ToolDefError(
                    f"tool id {td.id!r} collides with an existing catalog tool"
                )
            TOOLS.register(td.id, tool_def_to_spec(td))
            added.append(td.id)
        yield
    finally:
        for tool_id in added:
            if TOOLS.contains(tool_id):
                TOOLS.unregister(tool_id)


def validate_tool_def(td: ToolDef) -> dict[str, Any]:
    """Validate one authored tool and echo its derived JSON Schema."""
    try:
        spec = tool_def_to_spec(td)
    except ToolDefError as exc:
        return {"id": td.id, "ok": False, "error": str(exc)}
    return {
        "id": td.id,
        "ok": True,
        "arg_schema": spec.arg_schema.model_json_schema(),
        "return_schema": (
            spec.return_schema.model_json_schema()
            if spec.return_schema is not None
            else None
        ),
    }


_TOOLS_MODULE_TEMPLATE = '''"""Auto-generated tool stubs for UI-authored tools.

Each tool below was authored in Agent Studio with a typed signature but no body.
Fill in each ``*_impl`` function with a real implementation. Until you do, calling
the tool raises ``NotImplementedError``. This module registers the tools into the
framework catalog on import, so the agent loaders next to it resolve their grants.
"""

from typing import Any

from pydantic import create_model

from agentfactory.catalog.io_types import IO_TYPES
from agentfactory.catalog.tools import TOOLS, ToolSpec

# Compact, serialisable definitions: {{id, description, args, returns}}.
_TOOL_DEFS: list[dict[str, Any]] = {tool_defs!r}


def _build_model(name: str, fields: dict[str, Any]) -> Any:
    definitions: dict[str, Any] = {{}}
    for field_name, spec in fields.items():
        py_type = IO_TYPES.get(spec["type_key"]).python_type
        if spec.get("required", True):
            definitions[field_name] = (py_type, ...)
        else:
            definitions[field_name] = (py_type | None, None)
    return create_model(name, **definitions)


def _stub(tool_id: str) -> Any:
    def _impl(**kwargs: Any) -> Any:
        raise NotImplementedError(
            f"tool {{tool_id!r}} needs an implementation; fill in this callable"
        )

    return _impl


def _model_name(tool_id: str, suffix: str) -> str:
    parts = tool_id.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts if p) + suffix


for _td in _TOOL_DEFS:
    if TOOLS.contains(_td["id"]):
        continue
    _args = _build_model(_model_name(_td["id"], "Args"), _td["args"])
    _ret = (
        _build_model(_model_name(_td["id"], "Result"), _td["returns"])
        if _td["returns"]
        else None
    )
    TOOLS.register(
        _td["id"],
        ToolSpec(
            id=_td["id"],
            description=_td["description"],
            arg_schema=_args,
            return_schema=_ret,
            callable=_stub(_td["id"]),
        ),
    )
'''


def render_tools_module(tool_defs: Iterable[ToolDef]) -> str:
    """Render the source of a ``_tools.py`` stub module for export."""
    serialised = [td.model_dump() for td in tool_defs]
    return _TOOLS_MODULE_TEMPLATE.format(tool_defs=serialised)
