"""MLOps lifecycle, model provenance, genuine retraining, and rollback endpoints."""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel

from flairguard.service.schemas import ModelMetadataResponse, RetrainRequest, RetrainResponse
from flairguard.service.models_registry import model_registry
from flairguard.mlops.pipeline import retraining_engine
from flairguard.storage import WorkOrderStore
from flairguard.service.config import settings

router = APIRouter(prefix="/api/v1/models", tags=["MLOps & Lifecycle"])


@router.get('/history')
def model_history():
    return model_registry.history()


class RollbackRequest(BaseModel):
    dataset: str = "FD002"


@router.get("", response_model=List[ModelMetadataResponse])
def list_models():
    """List loaded model bundles, version provenance, and benchmark performance."""
    models_dict = model_registry.list_models()
    result = []
    for ds, meta in models_dict.items():
        result.append(ModelMetadataResponse(
            dataset=meta["dataset"],
            model_id=meta["model_id"],
            model_type=meta["model_type"],
            champion=meta["champion"],
            features_count=meta["features_count"],
            target_cap=meta["target_cap"],
            metrics=meta["metrics"],
            provenance=meta["provenance"],
        ))
    return result


@router.post("/retrain", response_model=RetrainResponse)
def trigger_retraining(req: RetrainRequest = Body(...)):
    """Simulate arrival of newly completed labeled engine trajectories and run real challenger training.
    
    Fits actual scikit-learn / LightGBM models on newly available labeled data,
    evaluates on held-out validation engines, logs real metrics to MLflow, and
    performs atomic serving promotion only if the evaluation hurdle is passed.
    """
    try:
        # Hurdle: require >= 2.0% improvement for promotion
        result = retraining_engine.run_training_job(
            dataset=req.dataset,
            challenger_algorithm=req.challenger_model,
            reveal_batch_size=req.reveal_batch_size,
            hurdle_pct=2.0,
        )
        return RetrainResponse(
            candidate_model=result["challenger_algorithm"],
            dataset=result["dataset"],
            previous_rmse=round(result["previous_rmse"], 2),
            new_rmse=round(result["new_rmse"], 2),
            improvement_pct=round(result["improvement_pct"], 2),
            gate_passed=result["gate_passed"],
            promoted_to_champion=result["promoted_to_champion"],
            message=result["message"],
            mlflow_run_id=result.get("mlflow_run_id"),
            mlflow_experiment_name=result.get("mlflow_experiment_name"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retraining failed: {str(e)}")


@router.post("/rollback")
def rollback_model(req: RollbackRequest = Body(...)):
    """Roll back active serving model to the previous champion version."""
    ds = req.dataset.upper()
    try:
        outcome = model_registry.rollback_champion(ds)
        return {
            "status": "SUCCESS",
            "message": f"Successfully rolled back {ds} serving model to previous champion: {outcome['active_model_id']}",
            "rollback_details": outcome,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs")
def list_training_jobs(limit: int = Query(20, ge=1, le=100)):
    """List historical training jobs and promotion audit records from SQLite."""
    store = WorkOrderStore(settings.db_path, namespace="mlops_system")
    return store.list_training_jobs(limit=limit)
