"""Pydantic request and response schemas for FlairGuard AI API contracts."""
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field


# --- Health & Status ---
class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    database_connected: bool
    models_loaded: List[str]


# --- Fleet Management ---
class DatasetInfo(BaseModel):
    id: str
    name: str
    operating_conditions: int
    fault_modes: int
    train_engines: int
    test_engines: int
    total_records: int
    description: str


class EngineSummary(BaseModel):
    engine_id: int
    dataset: str
    total_cycles: int
    last_observed_cycle: int
    current_status: Literal["NOMINAL", "MONITOR", "MEDIUM", "HIGH", "CRITICAL", "ESCALATE_HUMAN", "UNKNOWN"]
    last_predicted_rul: Optional[float] = None
    last_prediction_usable: bool = True
    active_work_order_id: Optional[str] = None


class FleetSummary(BaseModel):
    dataset: str
    total_engines: int
    monitored_engines: int
    nominal_count: int
    warning_count: int
    critical_count: int
    active_work_orders: int
    telemetry_fault_count: int
    active_model_id: str


# --- Prediction Serving ---
class PredictRequest(BaseModel):
    dataset: Literal["FD001", "FD002"] = "FD002"
    engine_id: int = 1
    cycle: int
    settings: List[float] = Field(..., min_length=3, max_length=3)
    sensors: Dict[str, float] = Field(..., description="Sensor telemetry channels (sensor_1 through sensor_21)")
    history: Optional[List[Dict[str, float]]] = None


class QualityDetails(BaseModel):
    is_valid: bool
    quality_code: str
    details: Dict[str, Any] = Field(default_factory=dict)


class PredictResponse(BaseModel):
    engine_id: int
    cycle: int
    dataset: str
    model_id: str
    predicted_rul: Optional[float]
    raw_prediction: Optional[float]
    usable: bool
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    regime_id: Optional[int] = None
    anomaly_score: Optional[float] = None
    anomaly_threshold: Optional[float] = None
    persistence_count: int = 0
    quality: QualityDetails
    recommended_action: str
    recommended_severity: str
    decision_reason: str


# --- Replay & Simulation Lab ---
class ReplayStartRequest(BaseModel):
    dataset: Literal["FD001", "FD002"] = "FD002"
    engine_id: int
    split: Literal["train", "test"] = "test"
    policy: Literal["point", "fixed", "none", "quality_gate", "learned_gate"] = "point"
    namespace: Optional[str] = None


class FaultInjectionRequest(BaseModel):
    fault_type: Literal["stuck_sensor", "sensor_drift", "missing_data", "gaussian_noise"]
    channel: str = "sensor_11"
    start_cycle: int = 130
    duration: int = 20
    magnitude: float = 1.0


class ReplayStepRequest(BaseModel):
    step_count: int = Field(default=1, ge=1, le=100)


class ReplayStateResponse(BaseModel):
    session_id: str
    dataset: str
    engine_id: int
    split: str
    policy: str
    current_cycle: int
    total_trajectory_cycles: int
    is_completed: bool
    active_fault: Optional[Dict[str, Any]] = None
    last_evidence: Optional[Dict[str, Any]] = None
    active_work_order: Optional[Dict[str, Any]] = None


# --- Work Orders & Transitions ---
class WorkOrderResponse(BaseModel):
    work_order_id: str
    namespace: str
    asset_id: str
    engine_id: int
    cycle: int
    severity: str
    priority: str
    review_required: bool
    status: str
    action_type: str
    predicted_rul: Optional[float]
    anomaly_score: Optional[float]
    persistence_count: int
    decision_reason: str
    due_cycle: Optional[int]
    created_at: str
    updated_at: str


class WorkOrderTransitionRequest(BaseModel):
    target_status: Literal["ACKNOWLEDGED", "IN_PROGRESS", "CLOSED", "CANCELLED"]
    reason: str = "Manual operator review"
    resolution_notes: Optional[str] = None


class AuditEventResponse(BaseModel):
    log_id: int
    namespace: str
    engine_id: int
    cycle: int
    event_type: str
    work_order_id: Optional[str]
    decision_reason: str
    timestamp: str


# --- MLOps & Model Info ---
class ModelMetadataResponse(BaseModel):
    dataset: str
    model_id: str
    model_type: str
    champion: bool
    features_count: int
    target_cap: int
    metrics: Dict[str, float]
    provenance: Dict[str, Any]


class RetrainRequest(BaseModel):
    dataset: Literal["FD001", "FD002"] = "FD002"
    challenger_model: str = "LightGBM_Optuna"
    reveal_batch_size: int = 10


class RetrainResponse(BaseModel):
    candidate_model: str
    dataset: str
    previous_rmse: float
    new_rmse: float
    improvement_pct: float
    gate_passed: bool
    promoted_to_champion: bool
    message: str
    mlflow_run_id: Optional[str] = None
    mlflow_experiment_name: Optional[str] = None

