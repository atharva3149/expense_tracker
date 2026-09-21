"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import AuthConfig, auth_dependency
from .db import Database
from .routes import public_router, router

PROJECT_DIR = Path(__file__).resolve().parent.parent
REACT_DIST_DIR = PROJECT_DIR / "frontend" / "dist"


def create_app(
    db_path: str = "data/spend.db",
    api_key: str | None = None,
    jwt_secret: str | None = None,
    jwt_expire_minutes: int = 1440,
    cors_origins: list[str] | None = None,
    serve_static: bool = True,
) -> FastAPI:
    app = FastAPI(
        title="Spend Tracker API",
        version="1.0.0",
        description="Log expenses and get a simple monthly summary.",
    )
    app.state.db = Database(db_path)
    app.state.auth = AuthConfig(api_key, jwt_secret, jwt_expire_minutes)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins
        or ["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(public_router)
    app.include_router(router, dependencies=[auth_dependency(app.state.auth)])

    if serve_static and REACT_DIST_DIR.is_dir():
        app.mount("/", StaticFiles(directory=REACT_DIST_DIR, html=True), name="static")

    return app
