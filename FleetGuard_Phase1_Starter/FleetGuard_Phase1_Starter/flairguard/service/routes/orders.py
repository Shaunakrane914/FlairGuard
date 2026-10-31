"""Work order management and regulatory audit trail endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException, Path
from flairguard.service.schemas import (
    WorkOrderResponse,
    WorkOrderTransitionRequest,
    AuditEventResponse,
)
from flairguard.service.config import settings
from flairguard.storage import WorkOrderStore

router = APIRouter(prefix="/api/v1", tags=["Maintenance Operations"])


@router.get("/work-orders", response_model=List[WorkOrderResponse])
def list_work_orders(
    namespace: str = Query("default", description="Session or operational namespace"),
    status: Optional[str] = Query(None, description="Filter by status (OPEN, ACKNOWLEDGED, IN_PROGRESS, CLOSED, CANCELLED)"),
    severity: Optional[str] = Query(None, description="Filter by severity (CRITICAL, HIGH, MEDIUM)"),
    engine_id: Optional[int] = Query(None, description="Filter by engine ID"),
):
    """Query persistent work orders from SQLite with multi-criteria filtering."""
    store = WorkOrderStore(settings.db_path, namespace=namespace)
    all_orders = store.get_all_work_orders()
    
    filtered = []
    for o in all_orders:
        if status and o.get("status") != status:
            continue
        if severity and o.get("severity") != severity:
            continue
        if engine_id is not None and o.get("engine_id") != engine_id:
            continue
            
        filtered.append(WorkOrderResponse(
            work_order_id=o["work_order_id"],
            namespace=o["namespace"],
            asset_id=o["asset_id"],
            engine_id=o["engine_id"],
            cycle=o["cycle"],
            severity=o["severity"],
            priority=o["priority"],
            review_required=bool(o["review_required"]),
            status=o["status"],
            action_type=o["action_type"],
            predicted_rul=o.get("predicted_rul"),
            anomaly_score=o.get("anomaly_score"),
            persistence_count=o["persistence_count"],
            decision_reason=o["decision_reason"],
            due_cycle=o.get("due_cycle"),
            created_at=o["created_at"],
            updated_at=o["updated_at"],
        ))
        
    return filtered


@router.get("/work-orders/{wo_id}", response_model=WorkOrderResponse)
def get_work_order(
    wo_id: str = Path(..., description="Unique Work Order ID"),
    namespace: str = Query("default"),
):
    """Retrieve full details of a specific maintenance work order."""
    store = WorkOrderStore(settings.db_path, namespace=namespace)
    orders = [o for o in store.get_all_work_orders() if o["work_order_id"] == wo_id]
    if not orders:
        raise HTTPException(status_code=404, detail=f"Work order {wo_id} not found")
        
    o = orders[0]
    return WorkOrderResponse(
        work_order_id=o["work_order_id"],
        namespace=o["namespace"],
        asset_id=o["asset_id"],
        engine_id=o["engine_id"],
        cycle=o["cycle"],
        severity=o["severity"],
        priority=o["priority"],
        review_required=bool(o["review_required"]),
        status=o["status"],
        action_type=o["action_type"],
        predicted_rul=o.get("predicted_rul"),
        anomaly_score=o.get("anomaly_score"),
        persistence_count=o["persistence_count"],
        decision_reason=o["decision_reason"],
        due_cycle=o.get("due_cycle"),
        created_at=o["created_at"],
        updated_at=o["updated_at"],
    )


@router.post("/work-orders/{wo_id}/transition", response_model=WorkOrderResponse)
def transition_work_order(
    req: WorkOrderTransitionRequest,
    wo_id: str = Path(..., description="Unique Work Order ID"),
    namespace: str = Query("default"),
):
    """Execute authorized state transition on active work order."""
    store = WorkOrderStore(settings.db_path, namespace=namespace)
    try:
        updated = store.transition_work_order(
            work_order_id=wo_id,
            target_status=req.target_status,
            reason=req.reason
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    return WorkOrderResponse(
        work_order_id=updated["work_order_id"],
        namespace=updated["namespace"],
        asset_id=updated["asset_id"],
        engine_id=updated["engine_id"],
        cycle=updated["cycle"],
        severity=updated["severity"],
        priority=updated["priority"],
        review_required=bool(updated["review_required"]),
        status=updated["status"],
        action_type=updated["action_type"],
        predicted_rul=updated.get("predicted_rul"),
        anomaly_score=updated.get("anomaly_score"),
        persistence_count=updated["persistence_count"],
        decision_reason=updated["decision_reason"],
        due_cycle=updated.get("due_cycle"),
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
    )


@router.get("/audit-log", response_model=List[AuditEventResponse])
def get_audit_log(
    namespace: str = Query("default"),
    engine_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """Query immutable audit events recorded by the platform."""
    store = WorkOrderStore(settings.db_path, namespace=namespace)
    events = store.get_audit_trail(engine_id=engine_id)
    
    return [
        AuditEventResponse(
            log_id=e["log_id"],
            namespace=e["namespace"],
            engine_id=e["engine_id"],
            cycle=e["cycle"],
            event_type=e["event_type"],
            work_order_id=e.get("work_order_id"),
            decision_reason=e["decision_reason"],
            timestamp=e["timestamp"],
        )
        for e in events[:limit]
    ]
