"""AgentComposer API — a stateless authoring backend over AgentFactory.

Era II: turns the framework into something a UI, a script, or a CI job can
drive over HTTP. It imports the framework; the framework never imports it.
"""

from __future__ import annotations

from composer.app import app, create_app

__all__ = ["app", "create_app"]
