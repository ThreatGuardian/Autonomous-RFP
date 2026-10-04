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
    problems = get_settings().check_production()
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))
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
    docs = None if settings.production else "/docs"
    app = FastAPI(title="Tenderdesk API", version=__version__, lifespan=lifespan, docs_url=docs, redoc_url=None,
                  openapi_url=None if settings.production else "/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type"])
    # Every /api route except sign-in and health requires a valid session cookie.
    public = ("/api/auth/", "/api/health")
    unsafe = {"POST", "PUT", "PATCH", "DELETE"}

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            # Cross-site request forgery: a state-changing call must come from this site or an allowed origin.
            origin = request.headers.get("origin")
            if request.method in unsafe and origin:
                own = f"{request.url.scheme}://{request.url.netloc}"
                if origin.rstrip("/") != own and origin.rstrip("/") not in get_settings().allowed_origins:
                    return JSONResponse({"detail": "Cross-origin request refused"}, status_code=403)
            if (get_settings().require_auth and not path.startswith(public)
                    and auth.current_user_id(request) is None):
                return JSONResponse({"detail": "Not signed in"}, status_code=401)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if get_settings().cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

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
