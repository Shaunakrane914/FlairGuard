"""Health and readiness endpoints."""
from fastapi import APIRouter
from flairguard.service.config import settings
from flairguard.service.schemas import HealthResponse
from flairguard.service.models_registry import model_registry
from flairguard.storage import WorkOrderStore

router = APIRouter(prefix="/api/v1", tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def check_health():
    """Verify backend health, database connection, and loaded models."""
    db_ok = False
    try:
        store = WorkOrderStore(settings.db_path, namespace="health_check")
        with store._get_connection() as conn:
            cursor = conn.execute("SELECT 1")
            db_ok = cursor.fetchone()[0] == 1
    except Exception:
        db_ok = False

    models_loaded = list(model_registry.list_models().keys())
    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        app_name=settings.app_name,
        version=settings.app_version,
        database_connected=db_ok,
        models_loaded=models_loaded,
    )
