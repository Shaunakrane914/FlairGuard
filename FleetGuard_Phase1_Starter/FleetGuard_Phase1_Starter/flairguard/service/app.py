"""Main FastAPI application factory for FlairGuard AI Platform."""
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from .config import settings
from .models_registry import model_registry
from .routes import health, fleet, predictions, replay, orders, mlops


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

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Route registration
    app.include_router(health.router)
    app.include_router(fleet.router)
    app.include_router(predictions.router)
    app.include_router(replay.router)
    app.include_router(orders.router)
    app.include_router(mlops.router)

    # Static frontend hosting if built
    dist_path = Path(__file__).resolve().parents[4] / "frontend" / "dist"
    if dist_path.is_dir():
        app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="frontend")

    # Custom global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": "InternalServerError",
                "message": str(exc),
                "path": request.url.path,
            }
        )

    return app


app = create_app()

