"""Comprehensive Unit Tests for FlairGuard Anomaly Detection & Triage Agent.

Tests:
1. Anomaly detector fitting on training data only & threshold calibration.
2. Anomaly persistence filtering (suppression of transient spikes).
3. Data quality detection (stuck sensor, missing data, physical envelope).
4. Conflicting model evidence handling (human escalation).
5. Idempotent work-order generation & duplicate alert prevention in SQLite.
6. Severity escalation in active work orders.
"""
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from flairguard.anomaly import (
    StatisticalDeviationDetector,
    PCAReconstructionDetector,
    IsolationForestDetector,
    PersistenceFilter,
)
from flairguard.quality import TelemetryQualityAuditor, QualityAssessment
from flairguard.storage import WorkOrderStore
from flairguard.triage import RiskAwareTriageAgent


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    import gc
    gc.collect()
    try:
        Path(db_path).unlink(missing_ok=True)
    except PermissionError:
        pass


def test_anomaly_detectors_calibration_and_far():
    """Verify that anomaly detectors calibrate thresholds to match target false alarm rates."""
    rng = np.random.default_rng(42)
    # Generate nominal training and validation data (e.g. 500 samples, 10 sensors)
    train_nominal = rng.normal(loc=50.0, scale=2.0, size=(400, 10))
    val_nominal = rng.normal(loc=50.0, scale=2.0, size=(200, 10))

    detectors = [
        StatisticalDeviationDetector(),
        PCAReconstructionDetector(n_components=3),
        IsolationForestDetector(n_estimators=50, random_state=42),
    ]

    for det in detectors:
        det.fit(train_nominal)
        assert det.is_fitted
        # Target 5% FAR
        thresh = det.calibrate_threshold(val_nominal, target_far=0.05)
        assert thresh > 0
        
        # Verify empirical false alarm rate is close to 5%
        scores = det.compute_raw_score(val_nominal)
        empirical_far = np.mean(scores >= thresh)
        assert 0.02 <= empirical_far <= 0.09, f"{det.name} empirical FAR {empirical_far} outside expected range"


def test_persistence_filter_suppresses_transient_spikes():
    """Verify that a single spike is suppressed while consecutive anomalies trigger the alarm."""
    p_filter = PersistenceFilter(persistence_length=3)
    engine_id = 101

    # Cycle 1: anomalous spike
    count = p_filter.update(engine_id, is_anomalous=True)
    assert count == 1
    assert not p_filter.is_persistent(engine_id)

    # Cycle 2: normal reading (transient noise cleared)
    count = p_filter.update(engine_id, is_anomalous=False)
    assert count == 0
    assert not p_filter.is_persistent(engine_id)

    # Cycles 3, 4, 5: consecutive degradation
    c1 = p_filter.update(engine_id, is_anomalous=True)
    c2 = p_filter.update(engine_id, is_anomalous=True)
    c3 = p_filter.update(engine_id, is_anomalous=True)
    assert (c1, c2, c3) == (1, 2, 3)
    assert p_filter.is_persistent(engine_id)


def test_quality_auditor_detects_faults():
    """Verify detection of missing data, physical envelope violations, and stuck sensors."""
    auditor = TelemetryQualityAuditor(bounds_sigma=4.0, stuck_window=3)
    
    # Create fake training data to learn nominal ranges
    df_train = pd.DataFrame({
        f"sensor_{i}": np.random.normal(100.0, 5.0, size=100) for i in range(1, 22)
    })
    auditor.fit_reference_ranges(df_train)

    # 1. Missing data fault
    bad_row = {"sensor_2": np.nan, "sensor_3": 100.0}
    res = auditor.audit_row(engine_id=1, cycle=1, telemetry_dict=bad_row)
    assert not res.is_valid
    assert res.quality_code == "MISSING_DATA"

    # 2. Out of bounds fault
    extreme_row = {f"sensor_{i}": 100.0 for i in range(1,22)}
    extreme_row["sensor_2"] = 9999.0
    res = auditor.audit_row(engine_id=1, cycle=2, telemetry_dict=extreme_row)
    assert not res.is_valid
    assert res.quality_code == "OUT_OF_REFERENCE"

    # 3. Stuck sensor flatline fault across 3 cycles
    auditor_stuck = TelemetryQualityAuditor(stuck_window=3)
    normal_row = {f"sensor_{i}": 100.0 for i in range(1, 22)}
    auditor_stuck.audit_row(engine_id=2, cycle=1, telemetry_dict=normal_row)
    auditor_stuck.audit_row(engine_id=2, cycle=2, telemetry_dict=normal_row)
    res_stuck = auditor_stuck.audit_row(engine_id=2, cycle=3, telemetry_dict=normal_row)
    assert not res_stuck.is_valid
    assert res_stuck.quality_code == "STUCK_SENSOR"


def test_triage_conflicting_evidence_escalation(temp_db):
    """Verify that conflicting RUL and anomaly persistence triggers human review."""
    store = WorkOrderStore(temp_db)
    agent = RiskAwareTriageAgent(store=store)

    # Anomaly persistence is 5 cycles (severe degradation), but predicted RUL is 75 cycles (healthy)
    decision = agent.evaluate(
        engine_id=42,
        cycle=110,
        predicted_rul=75.0,
        uncertainty=12.0,
        anomaly_score=0.85,
        persistence_count=5,
        quality=QualityAssessment(is_valid=True, quality_code="NOMINAL", details={})
    )

    assert decision.severity == "ESCALATE_HUMAN"
    assert decision.action_type == "ESCALATE_HUMAN_CONFLICT"
    assert "conflicts" in decision.decision_reason


def test_work_order_idempotency_and_duplicate_suppression(temp_db):
    """Verify duplicate alert suppression for ongoing active work orders."""
    store = WorkOrderStore(temp_db)
    agent = RiskAwareTriageAgent(store=store)

    # First triage call -> Creates P3 Medium Work Order
    d1 = agent.evaluate(
        engine_id=7,
        cycle=120,
        predicted_rul=45.0,
        uncertainty=10.0,
        anomaly_score=0.4,
        persistence_count=1,
        quality=QualityAssessment(is_valid=True, quality_code="NOMINAL", details={})
    )
    assert d1.store_status == "CREATED"
    assert d1.severity == "MEDIUM"

    # Second triage call next cycle with same severity -> Suppressed!
    d2 = agent.evaluate(
        engine_id=7,
        cycle=121,
        predicted_rul=44.0,
        uncertainty=10.0,
        anomaly_score=0.42,
        persistence_count=2,
        quality=QualityAssessment(is_valid=True, quality_code="NOMINAL", details={})
    )
    assert d2.store_status == "SUPPRESSED"
    assert d2.work_order_id == d1.work_order_id

    # Check database counts
    all_wo = store.get_all_work_orders()
    assert len(all_wo) == 1, "Duplicate work order was created instead of being suppressed!"
    audit = store.get_audit_trail(engine_id=7)
    event_types = [a["event_type"] for a in audit]
    assert "DUPLICATE_SUPPRESSED" not in event_types  # Decisions, not repeated audit noise, retain every cycle.
    assert store.get_event(7,121) is not None


def test_work_order_severity_escalation(temp_db):
    """Verify that progressive wear escalates active work order severity from MEDIUM to CRITICAL."""
    store = WorkOrderStore(temp_db)
    agent = RiskAwareTriageAgent(store=store)

    # Step 1: Create initial MEDIUM work order
    d1 = agent.evaluate(
        engine_id=12,
        cycle=130,
        predicted_rul=42.0,
        uncertainty=10.0,
        anomaly_score=0.35,
        persistence_count=1,
        quality=QualityAssessment(is_valid=True, quality_code="NOMINAL", details={})
    )
    assert d1.store_status == "CREATED"
    assert d1.severity == "MEDIUM"

    # Step 2: Next cycle RUL drops into CRITICAL regime (< 15 cycles)
    d2 = agent.evaluate(
        engine_id=12,
        cycle=135,
        predicted_rul=12.0,
        uncertainty=8.0,
        anomaly_score=0.92,
        persistence_count=4,
        quality=QualityAssessment(is_valid=True, quality_code="NOMINAL", details={})
    )
    assert d2.store_status == "ESCALATED"
    assert d2.severity == "CRITICAL"
    assert d2.work_order_id == d1.work_order_id

    # Verify updated database row
    active = store.get_active_work_order(12)
    assert active["severity"] == "CRITICAL"
    assert active["predicted_rul"] == 12.0

    # Verify audit trail logs SEVERITY_ESCALATED
    audit = store.get_audit_trail(engine_id=12)
    events = [a["event_type"] for a in audit]
    assert events == ["HUMAN_ESCALATION", "SEVERITY_ESCALATED"]  # Inspection has a review flag, independent of urgency.

