"""Main FastAPI application factory for FlairGuard AI Platform."""
from pathlib import Path
import logging
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from .config import settings
from .models_registry import model_registry
from .routes import health, fleet, predictions, replay, orders, mlops, evidence, reliability

logger = logging.getLogger("flairguard.service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load verified model artifacts on startup."""
    model_registry.load_models()
    yield


def create_app() -> FastAPI:
    """Build and configure production-style FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Connected Fleet Reliability & Predictive Maintenance Platform — Tata Elxsi Teliport S4 Case Study 1.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def protect_mutations(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin and origin not in settings.cors_origins:
                return JSONResponse(status_code=403, content={"detail": "Untrusted origin"})
            if not settings.api_key:
                return JSONResponse(status_code=503, content={"detail": "State changes disabled: configure FLAIRGUARD_API_KEY"})
            if not secrets.compare_digest(request.headers.get("x-api-key", ""), settings.api_key):
                return JSONResponse(status_code=401, content={"detail": "Valid operator API key required"})
        return await call_next(request)

    # CORS configuration - strict trusted localhost development & deployment origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Route registration
    app.include_router(health.router)
    app.include_router(fleet.router)
    app.include_router(predictions.router)
    app.include_router(replay.router)
    app.include_router(orders.router)
    app.include_router(mlops.router)
    app.include_router(evidence.router)
    app.include_router(reliability.router)

    # Static frontend hosting if built (searches both container and local paths)
    candidate_paths = [
        Path(__file__).resolve().parents[4] / "frontend" / "dist" if len(Path(__file__).resolve().parents) >= 5 else None,
        Path(__file__).resolve().parents[2] / "frontend" / "dist" if len(Path(__file__).resolve().parents) >= 3 else None,
        Path("/app/frontend/dist"),
        Path.cwd() / "frontend" / "dist",
    ]
    dist_path = next((p for p in candidate_paths if p is not None and p.is_dir()), None)
    if dist_path:
        app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="frontend")

    # Sanitized global exception handler preventing information leakage
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled service exception at %s: %s", request.url.path, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "InternalServerError",
                "message": "An internal service error occurred. See the server log.",
                "path": request.url.path,
            }
        )

    return app


app = create_app()
