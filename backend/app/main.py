"""FastAPI application entry point."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.agents.orchestrator import get_orchestrator, shutdown_orchestrator
from app.api import auth, data, reference, report, rfps
from app.config import get_settings
from app.db.seed import seed_all
from app.market.service import market_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tenderdesk")


def _warm_up() -> None:
    """Train or load models and build indexes so the first request is fast."""
    from app.finance.currency import fx
    from app.ml.registry import registry
    from app.rag.stores import catalogue_store, knowledge_store

    try:
        registry.describe()
        knowledge_store()
        catalogue_store()
        fx.snapshot()
        log.info("Models, indexes and exchange rates ready")
    except Exception:  # pragma: no cover
        log.exception("Warm-up failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    seed_all()
    auth.seed_demo_user()
    _warm_up_thread = threading.Thread(target=_warm_up, daemon=True)
    _warm_up_thread.start()
    recovered = get_orchestrator().recover()
    if recovered:
        log.info("Re-queued %d interrupted request(s)", recovered)
    yield
    shutdown_orchestrator()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Tenderdesk API", version=__version__, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])
    # Every /api route except sign-in and health requires a valid session cookie.
    public = ("/api/auth/", "/api/health")

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        path = request.url.path
        if (get_settings().require_auth and path.startswith("/api/") and not path.startswith(public)
                and auth.current_user_id(request) is None):
            return JSONResponse({"detail": "Not signed in"}, status_code=401)
        return await call_next(request)

    app.include_router(auth.router)
    app.include_router(rfps.router)
    app.include_router(report.router)
    app.include_router(reference.router)
    app.include_router(data.router)
    app.mount("/market-api", market_app)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    dist = settings.frontend_dist
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
