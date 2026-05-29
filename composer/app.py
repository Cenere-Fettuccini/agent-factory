"""FastAPI application factory for the AgentComposer API.

Stateless: every request carries its own graph; the server holds no session
state, so restarting it changes nothing for clients.
"""

from __future__ import annotations

from fastapi import FastAPI

from composer.routers import authoring, introspection


def create_app() -> FastAPI:
    """Build the AgentComposer FastAPI app with all routers mounted."""
    app = FastAPI(
        title="AgentComposer API",
        version="0.1.0",
        description=(
            "Stateless authoring backend for the AgentFactory framework. "
            "Exposes the framework's catalogs, schemas, and validation over HTTP."
        ),
    )
    app.include_router(introspection.router)
    app.include_router(authoring.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
