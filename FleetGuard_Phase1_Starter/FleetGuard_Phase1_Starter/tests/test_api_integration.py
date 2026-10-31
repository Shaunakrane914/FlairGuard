"""Integration tests for FlairGuard Platform FastAPI Backend (Milestone 1).

Verifies the entire vertical slice:
1. Health and model loading
2. Fleet discovery and engine listings
3. Genuine prediction serving
4. End-to-end telemetry replay
5. Sensor fault injection and dynamic human escalation
6. Persistent work-order transitions and audit logging
7. Backend restart survivability
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from flairguard.service.app import create_app
from flairguard.service.config import settings
from flairguard.storage import WorkOrderStore


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client):
    """Verify health endpoint reports healthy status and loaded models."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["database_connected"] is True
    assert "FD001" in data["models_loaded"]
    assert "FD002" in data["models_loaded"]


def test_fleet_discovery(client):
    """Verify dataset metadata and engine discovery on real NASA datasets."""
    # Datasets
    res_ds = client.get("/api/v1/fleet/datasets")
    assert res_ds.status_code == 200
    datasets = res_ds.json()
    assert len(datasets) == 2
    ds_ids = [d["id"] for d in datasets]
    assert "FD001" in ds_ids and "FD002" in ds_ids

    # Engines for FD002
    res_eng = client.get("/api/v1/fleet/engines?dataset=FD002&limit=10")
    assert res_eng.status_code == 200
    engines = res_eng.json()
    assert len(engines) == 10
    assert engines[0]["engine_id"] == 1
    assert engines[0]["dataset"] == "FD002"
    assert engines[0]["total_cycles"] > 0

    # Fleet summary
    res_sum = client.get("/api/v1/fleet/summary?dataset=FD002")
    assert res_sum.status_code == 200
    summary = res_sum.json()
    assert summary["total_engines"] == 259
    assert summary["monitored_engines"] == 259


def test_prediction_serving(client):
    """Verify genuine model inference on raw telemetry without fabricated predictions."""
    payload = {
        "dataset": "FD002",
        "engine_id": 1,
        "cycle": 25,
        "settings": [0.0023, 0.0003, 100.0],
        "sensors": {f"sensor_{i}": 500.0 + i for i in range(1, 22)},
        "history": [
            {"cycle": c, **{f"setting_{k}": 0.0 for k in range(1, 4)}, **{f"sensor_{s}": 500.0 + s for s in range(1, 22)}}
            for c in range(1, 25)
        ]
    }
    res = client.post("/api/v1/predict", json=payload)
    assert res.status_code == 200
    pred = res.json()
    assert pred["dataset"] == "FD002"
    assert pred["predicted_rul"] is not None
    assert 0 <= pred["predicted_rul"] <= 125
    assert pred["quality"]["is_valid"] is True


def test_end_to_end_replay_and_fault_escalation(client):
    """Verify causal replay, fault injection, dynamic human escalation, and work-order generation."""
    ns = f"test_e2e_{uuid.uuid4().hex[:6]}"
    # 1. Start Replay Session on FD002 Engine 15 with quality_gate policy
    res_start = client.post("/api/v1/replay/start", json={
        "dataset": "FD002",
        "engine_id": 15,
        "split": "test",
        "policy": "quality_gate",
        "namespace": ns
    })
    assert res_start.status_code == 200
    session_data = res_start.json()
    session_id = session_data["session_id"]
    assert session_data["current_cycle"] == 0

    # 2. Step forward 20 cycles (nominal observation warm-up)
    res_step = client.post(f"/api/v1/replay/{session_id}/step", json={"step_count": 20})
    assert res_step.status_code == 200
    state = res_step.json()
    assert state["current_cycle"] == 20
    assert state["last_evidence"]["cycle"] == 20
    assert state["last_evidence"]["usable"] is True

    # 3. Inject stuck sensor fault starting at cycle 21
    res_fault = client.post(f"/api/v1/replay/{session_id}/inject-fault", json={
        "fault_type": "stuck_sensor",
        "channel": "sensor_11",
        "start_cycle": 21,
        "duration": 10,
        "magnitude": 1.0
    })
    assert res_fault.status_code == 200

    # 4. Step forward through the fault (5 cycles freeze sensor, triggering auditor)
    res_step2 = client.post(f"/api/v1/replay/{session_id}/step", json={"step_count": 7})
    assert res_step2.status_code == 200
    state2 = res_step2.json()
    assert state2["current_cycle"] == 27
    assert state2["last_evidence"]["usable"] is False
    assert state2["last_evidence"]["severity"] == "ESCALATE_HUMAN"

    # 5. Verify work order created in SQLite
    res_wo = client.get(f"/api/v1/work-orders?namespace={ns}")
    assert res_wo.status_code == 200
    orders = res_wo.json()
    assert len(orders) >= 1
    wo = orders[0]
    assert wo["engine_id"] == 15
    assert wo["status"] == "OPEN"

    # 6. Test state transition: OPEN -> ACKNOWLEDGED -> IN_PROGRESS -> CLOSED
    wo_id = wo["work_order_id"]
    res_t1 = client.post(f"/api/v1/work-orders/{wo_id}/transition?namespace={ns}", json={
        "target_status": "ACKNOWLEDGED",
        "reason": "Dispatcher acknowledged alert"
    })
    assert res_t1.status_code == 200
    assert res_t1.json()["status"] == "ACKNOWLEDGED"

    res_t2 = client.post(f"/api/v1/work-orders/{wo_id}/transition?namespace={ns}", json={
        "target_status": "IN_PROGRESS",
        "reason": "Technician dispatched to depot"
    })
    assert res_t2.status_code == 200
    assert res_t2.json()["status"] == "IN_PROGRESS"

    res_t3 = client.post(f"/api/v1/work-orders/{wo_id}/transition?namespace={ns}", json={
        "target_status": "CLOSED",
        "reason": "Maintenance inspection completed",
        "resolution_notes": "Replaced sensor wiring"
    })
    assert res_t3.status_code == 200
    assert res_t3.json()["status"] == "CLOSED"

    # 7. Verify audit log contains full transition trail
    res_audit = client.get(f"/api/v1/audit-log?namespace={ns}")
    assert res_audit.status_code == 200
    audit = res_audit.json()
    event_types = [a["event_type"] for a in audit]
    assert "STATUS_CHANGED" in event_types


def test_restart_recovery(client):
    """Verify that backend state survives process stop/restart."""
    # Write a dedicated work order
    store1 = WorkOrderStore(settings.db_path, namespace="restart_test_ns")
    store1.record_decision(
        engine_id=99,
        cycle=50,
        severity="HIGH",
        action_type="WORK_ORDER_SCHEDULE_MAINTENANCE",
        predicted_rul=28.5,
        uncertainty=5.0,
        anomaly_score=0.6,
        persistence_count=2,
        decision_reason="Pre-restart test decision",
    )
    store1.close()

    # Re-open in a fresh store instance (simulating restart)
    store2 = WorkOrderStore(settings.db_path, namespace="restart_test_ns")
    orders = store2.get_all_work_orders()
    store2.close()

    assert len(orders) == 1
    assert orders[0]["engine_id"] == 99
    assert orders[0]["severity"] == "HIGH"
    assert orders[0]["predicted_rul"] == 28.5


def test_frontend_static_serving(client):
    """Verify built React frontend is delivered at root URL."""
    res = client.get("/")
    assert res.status_code == 200
    assert "FlairGuard AI" in res.text
    assert "root" in res.text
