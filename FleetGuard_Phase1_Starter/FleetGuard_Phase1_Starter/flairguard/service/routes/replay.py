"""Telemetry replay and scenario lab endpoints."""
from fastapi import APIRouter, HTTPException
from flairguard.service.schemas import (
    ReplayStartRequest,
    ReplayStepRequest,
    FaultInjectionRequest,
    ReplayStateResponse,
)
from flairguard.service.replay_manager import replay_manager

router = APIRouter(prefix="/api/v1/replay", tags=["Simulation & Replay Lab"])


@router.post("/start", response_model=ReplayStateResponse)
def start_replay(req: ReplayStartRequest):
    """Initialize a causal replay session on real NASA engine telemetry."""
    try:
        session = replay_manager.create_session(
            dataset=req.dataset,
            engine_id=req.engine_id,
            split=req.split,
            policy_name=req.policy,
            namespace=req.namespace,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    return ReplayStateResponse(
        session_id=session.session_id,
        dataset=session.dataset,
        engine_id=session.engine_id,
        split=session.split,
        policy=session.policy_name,
        current_cycle=session.current_index,
        total_trajectory_cycles=session.total_cycles,
        is_completed=session.current_index >= session.total_cycles,
        active_fault=session.active_fault,
        last_evidence=session.last_evidence,
        active_work_order=session.store.get_active_work_order(session.engine_id, asset_id=str(session.engine_id)),
    )


@router.post("/{session_id}/step", response_model=ReplayStateResponse)
def step_replay(session_id: str, req: ReplayStepRequest):
    """Step forward causal telemetry consumption and trigger decision rules."""
    try:
        session = replay_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session.step(count=req.step_count)
    active_wo = session.store.get_active_work_order(session.engine_id, asset_id=str(session.engine_id))
    
    return ReplayStateResponse(
        session_id=session.session_id,
        dataset=session.dataset,
        engine_id=session.engine_id,
        split=session.split,
        policy=session.policy_name,
        current_cycle=session.current_index,
        total_trajectory_cycles=session.total_cycles,
        is_completed=session.current_index >= session.total_cycles,
        active_fault=session.active_fault,
        last_evidence=session.last_evidence,
        active_work_order=active_wo,
    )


@router.get("/{session_id}", response_model=ReplayStateResponse)
def get_replay_status(session_id: str):
    """Inspect current replay state and active work order."""
    try:
        session = replay_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
        
    active_wo = session.store.get_active_work_order(session.engine_id, asset_id=str(session.engine_id))
    return ReplayStateResponse(
        session_id=session.session_id,
        dataset=session.dataset,
        engine_id=session.engine_id,
        split=session.split,
        policy=session.policy_name,
        current_cycle=session.current_index,
        total_trajectory_cycles=session.total_cycles,
        is_completed=session.current_index >= session.total_cycles,
        active_fault=session.active_fault,
        last_evidence=session.last_evidence,
        active_work_order=active_wo,
    )


@router.post("/{session_id}/reset", response_model=ReplayStateResponse)
def reset_replay(session_id: str):
    """Reset replay back to cycle 1."""
    try:
        session = replay_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session.reset()
    active_wo = session.store.get_active_work_order(session.engine_id, asset_id=str(session.engine_id))
    return ReplayStateResponse(
        session_id=session.session_id,
        dataset=session.dataset,
        engine_id=session.engine_id,
        split=session.split,
        policy=session.policy_name,
        current_cycle=0,
        total_trajectory_cycles=session.total_cycles,
        is_completed=False,
        active_fault=session.active_fault,
        last_evidence=None,
        active_work_order=active_wo,
    )


@router.post("/{session_id}/inject-fault")
def inject_fault(session_id: str, req: FaultInjectionRequest):
    """Inject controlled synthetic telemetry fault into replay session."""
    try:
        session = replay_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session.inject_fault(
        fault_type=req.fault_type,
        channel=req.channel,
        start_cycle=req.start_cycle,
        duration=req.duration,
        magnitude=req.magnitude,
    )
    return {
        "status": "success",
        "session_id": session_id,
        "injected_fault": session.active_fault
    }
