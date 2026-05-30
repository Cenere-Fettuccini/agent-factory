"""FastAPI application factory for the AgentComposer API.

Stateless: every request carries its own graph; the server holds no session
state, so restarting it changes nothing for clients.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from composer.routers import authoring, introspection

# Origins allowed to call the API from a browser. The Agent Studio UI runs on a
# separate dev server, so without CORS the browser blocks every request. Default
# to the Vite dev origin; override with AGENTCOMPOSER_CORS_ORIGINS (comma-sep).
_DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def _cors_origins() -> list[str]:
    raw = os.environ.get("AGENTCOMPOSER_CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(introspection.router)
    app.include_router(authoring.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
