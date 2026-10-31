"""Unit and property tests for Fleet-Level Maintenance Optimization under depot constraints."""
import pytest
from flairguard.fleet_scheduler import (
    FleetMaintenanceScheduler,
    SchedulePolicy,
    build_profiles_from_dataset,
    EngineSimProfile,
)
from flairguard.service.config import settings


@pytest.fixture
def sample_profiles():
    """Load small deterministic fleet sample from FD002 test set."""
    return build_profiles_from_dataset(settings.data_dir, "FD002", engine_limit=15)


def test_scheduler_policy_execution(sample_profiles):
    """Verify all 4 policies complete without runtime exceptions."""
    scheduler = FleetMaintenanceScheduler(num_bays=2, service_duration=4, service_threshold_rul=25.0)
    for pol in SchedulePolicy:
        metrics = scheduler.simulate_fleet(sample_profiles, policy=pol)
        assert metrics.policy == pol.value
        assert metrics.total_engines_evaluated == len(sample_profiles)
        assert metrics.serviced_count >= 0
        assert metrics.total_fleet_cost >= 0.0
        assert 0.0 <= metrics.bay_utilization_pct <= 100.0


def test_bay_capacity_scaling(sample_profiles):
    """Increasing bay capacity should not increase queue waiting times."""
    scheduler_1bay = FleetMaintenanceScheduler(num_bays=1, service_duration=5, service_threshold_rul=25.0)
    scheduler_3bays = FleetMaintenanceScheduler(num_bays=3, service_duration=5, service_threshold_rul=25.0)

    m1 = scheduler_1bay.simulate_fleet(sample_profiles, policy=SchedulePolicy.RISK_AWARE)
    m3 = scheduler_3bays.simulate_fleet(sample_profiles, policy=SchedulePolicy.RISK_AWARE)

    assert m3.mean_queue_wait_cycles <= m1.mean_queue_wait_cycles
    assert m3.total_fleet_cost <= m1.total_fleet_cost


def test_comparison_evaluation_ranking(sample_profiles):
    """evaluate_comparison should return all 4 policies sorted by total fleet cost."""
    scheduler = FleetMaintenanceScheduler(num_bays=2, service_duration=4)
    comparison = scheduler.evaluate_comparison(sample_profiles)
    assert len(comparison) == 4
    # Verify sorted ascending by total fleet cost
    costs = [c.total_fleet_cost for c in comparison]
    assert costs == sorted(costs)


def test_live_snapshot_semantics(sample_profiles):
    """get_live_snapshot returns valid depot state with exact bay counts."""
    scheduler = FleetMaintenanceScheduler(num_bays=3, service_duration=4)
    snapshot = scheduler.get_live_snapshot(sample_profiles, target_cycle=110, policy=SchedulePolicy.RISK_AWARE)

    assert snapshot.num_bays == 3
    assert len(snapshot.bays) == 3
    assert snapshot.timestamp_cycle == 110
    assert snapshot.active_policy == "RISK_AWARE"
    for b in snapshot.bays:
        assert b.status in ("IDLE", "OCCUPIED")
        if b.status == "IDLE":
            assert b.engine_id is None
            assert b.cycles_remaining == 0
        else:
            assert b.engine_id is not None
            assert b.cycles_remaining > 0
