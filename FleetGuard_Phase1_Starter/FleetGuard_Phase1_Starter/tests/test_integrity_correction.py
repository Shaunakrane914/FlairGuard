"""Behavioral adversarial checks for leakage, executable timing and durable governance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor
from flairguard.fleet_scheduler import (EngineSimProfile, FleetMaintenanceScheduler,
    SchedulePolicy, build_profiles_from_dataset)
from flairguard.scheduler_evaluation import evaluate_fleet, load_failure_times
from flairguard.scheduler_scorer import score_events
from flairguard.service.config import settings
from flairguard.serving import predict_observations


def profile(eid=1, request=20, prediction=2., end=25):
    return EngineSimProfile(eid,end,[(request,prediction,0.)])


@pytest.mark.parametrize('failure,expected', [(23,'FAILURE'),(24,'FAILURE'),(25,'COMPLETE')])
def test_failure_during_service_and_completion_tie(failure,expected):
    scheduler = FleetMaintenanceScheduler(num_bays=1,service_duration=4)
    result = evaluate_fleet(scheduler,[profile()],{1:failure},SchedulePolicy.FCFS)
    assert result.events[-1]['kind'] == expected
    assert result.failure_count == (expected=='FAILURE')
    assert result.serviced_count + result.failure_count == 1


def test_terminal_positive_rul_keeps_decreasing_and_no_request_fails():
    scheduler = FleetMaintenanceScheduler(num_bays=1,service_duration=4)
    # Engine 2 waits behind engine 1, failing beyond last observed cycle 20.
    profiles = [profile(1,end=20),profile(2,end=20),EngineSimProfile(3,20,[(20,100.,0.)])]
    result = evaluate_fleet(scheduler,profiles,{1:100,2:25,3:27},SchedulePolicy.FCFS)
    failures = {e['engine_id']:e['cycle'] for e in result.events if e['kind']=='FAILURE'}
    assert failures == {2:25,3:27}
    assert result.serviced_count == 1
    assert result.censored_count == 0


def test_independent_scorer_rejects_forged_completion_and_missing_engine():
    scheduler = FleetMaintenanceScheduler(num_bays=1,service_duration=4)
    result = evaluate_fleet(scheduler,[profile()],{1:25},SchedulePolicy.FCFS)
    costs = dict(failure=10,service=1,waste=.05,delay=.1)
    scored = score_events(result.events,{1:25},1,4,costs)
    assert result.total_fleet_cost == scored['total_fleet_cost'] == pytest.approx(1.05)
    bad = [dict(e) for e in result.events]
    bad[-1]['cycle'] = 25
    with pytest.raises(AssertionError):
        score_events(bad,{1:25},1,4,costs)
    with pytest.raises(AssertionError):
        score_events(result.events,{1:25,2:50},1,4,costs)


def test_future_label_mutation_cannot_change_profiles_or_open_loop_dispatch(tmp_path):
    # A saved predictor and genuine telemetry. There is deliberately no train file.
    import shutil
    shutil.copyfile(settings.data_dir/'test_FD001.txt',tmp_path/'test_FD001.txt')
    model = DummyRegressor(strategy='constant',constant=12.).fit(pd.DataFrame({'cycle':[1,2]}),[1,2])
    bundle = dict(model=model,features=['cycle'],model_id='label-blind-test',min_history=20)
    (tmp_path/'RUL_FD001.txt').write_text('\n'.join(['100']*100))
    first = build_profiles_from_dataset(tmp_path,'FD001',3,bundle=bundle)
    world_a = load_failure_times(tmp_path,'FD001',[p.engine_id for p in first])
    (tmp_path/'RUL_FD001.txt').write_text('\n'.join(['1']*100))
    second = build_profiles_from_dataset(tmp_path,'FD001',3,bundle=bundle)
    world_b = load_failure_times(tmp_path,'FD001',[p.engine_id for p in second])
    assert world_a != world_b
    assert first == second
    scheduler = FleetMaintenanceScheduler()
    for policy in SchedulePolicy:
        assert scheduler.run(first,policy)['events'] == scheduler.run(second,policy)['events']
    # Stronger test: prediction builder must work when labels do not even exist.
    (tmp_path/'RUL_FD001.txt').unlink()
    assert first == build_profiles_from_dataset(tmp_path,'FD001',3,bundle=bundle)


def test_saved_predictions_equal_causal_prefix_and_labels_are_rejected():
    from flairguard.data import read_trajectories
    from flairguard.service.models_registry import model_registry
    raw = read_trajectories(settings.data_dir/'test_FD002.txt')
    raw = raw.loc[raw.engine_id==1].reset_index(drop=True)
    bundle = model_registry.get_bundle('FD002')
    full,_ = predict_observations(bundle,raw)
    prefix,_ = predict_observations(bundle,raw.iloc[:40].copy())
    np.testing.assert_allclose(full[:40],prefix,rtol=0,atol=1e-10)
    with pytest.raises(ValueError,match='labels'):
        predict_observations(bundle,raw.assign(true_rul=10))


def test_genuine_process_restart_promotion_rollback_and_tamper(tmp_path,monkeypatch):
    from flairguard.service.models_registry import ModelRegistry
    monkeypatch.setattr(settings,'fd001_bundle_path',tmp_path/'missing-a')
    monkeypatch.setattr(settings,'fd002_bundle_path',tmp_path/'missing-b')
    registry = ModelRegistry(tmp_path/'registry')
    def bundle(value):
        model = DummyRegressor(strategy='constant',constant=value).fit(pd.DataFrame({'cycle':[1,2]}),[1,2])
        return dict(model=model,features=['cycle'],model_id=f'actual-{value}',fit_engines=[1],rul_cap=125)
    def metadata(value):
        return dict(dataset='FD001',model_id=f'actual-{value}',model_type='test fitted predictor',metrics={},provenance={})
    registry.promote_challenger('FD001',bundle(5),metadata(5))
    registry.promote_challenger('FD001',bundle(2),metadata(2))
    code = '''
import sys,json,pandas as pd
from flairguard.service.models_registry import ModelRegistry
r=ModelRegistry(sys.argv[1])
b=r.get_bundle('FD001')
before=float(b['model'].predict(pd.DataFrame({'cycle':[20]}))[0])
r.rollback_champion('FD001')
after=float(r.get_bundle('FD001')['model'].predict(pd.DataFrame({'cycle':[20]}))[0])
print(json.dumps([before,after]))
'''
    env = dict(os.environ,FLAIRGUARD_FD001_BUNDLE_PATH=str(tmp_path/'missing-a'),FLAIRGUARD_FD002_BUNDLE_PATH=str(tmp_path/'missing-b'))
    child = subprocess.run([sys.executable,'-c',code,str(tmp_path/'registry')],env=env,capture_output=True,text=True,check=True)
    assert json.loads(child.stdout.strip().splitlines()[-1]) == [2.,5.]
    assert registry.get_bundle('FD001')['model_id'] == 'actual-5'
    path = registry.state_dir / registry.get_metadata('FD001')['provenance']['artifact_path']
    with path.open('ab') as stream:
        stream.write(b'tampered')
    with pytest.raises(RuntimeError,match='hash'):
        registry.get_bundle('FD001')


def test_champion_failure_blocks_training_and_promotion(tmp_path):
    from flairguard.mlops.pipeline import RetrainingEngine
    class Broken:
        def get_bundle(self,ds):
            raise RuntimeError('champion evaluation unavailable')
        def promote_challenger(self,*args):
            pytest.fail('Promotion after failed champion comparison')
    engine = RetrainingEngine(tmp_path/'jobs.db',registry=Broken())
    with pytest.raises(RuntimeError,match='champion evaluation unavailable'):
        engine.run_training_job()
    job = engine.store.list_training_jobs()[0]
    assert job['status']=='FAILED' and not job['promoted']
    assert job['previous_rmse'] is None


@pytest.mark.parametrize('route', ['/api/v1/models/retrain','/api/v1/models/rollback','/api/v1/replay/start','/api/v1/work-orders/example/transition','/api/v1/fleet/scheduler/simulate'])
def test_mutation_authentication_and_cross_origin(route,monkeypatch):
    from fastapi.testclient import TestClient
    from flairguard.service.app import create_app
    monkeypatch.setattr(settings,'api_key','operator-test-key')
    client = TestClient(create_app())
    assert client.post(route,json={}).status_code==401
    assert client.post(route,json={},headers={'X-API-Key':'wrong'}).status_code==401
    assert client.post(route,json={},headers={'X-API-Key':'operator-test-key','Origin':'https://untrusted.example'}).status_code==403
    monkeypatch.setattr(settings,'api_key','')
    assert client.post(route,json={}).status_code==503


def test_missing_or_corrupt_evidence_is_unavailable(tmp_path,monkeypatch):
    from flairguard.service.routes import evidence
    from fastapi import HTTPException
    monkeypatch.setattr(evidence,'ARTIFACTS_DIR',tmp_path)
    with pytest.raises(HTTPException) as exc:
        evidence.get_verified_benchmarks()
    assert exc.value.status_code==503


def test_scoring_keeps_uncapped_truth():
    from flairguard.metrics import regression_metrics
    assert regression_metrics([250],[125])['rmse_cycles']==125.


@pytest.mark.parametrize('failure_stage',['champion_prediction','mlflow_tracking'])
def test_real_fit_fails_closed_on_evaluation_or_required_tracking(tmp_path,monkeypatch,failure_stage):
    from flairguard.mlops import pipeline
    from flairguard.service.models_registry import model_registry
    engine = pipeline.RetrainingEngine(tmp_path/'jobs.db',registry=model_registry)
    if failure_stage=='champion_prediction':
        def unavailable(*args):
            raise RuntimeError('champion prediction failed')
        monkeypatch.setattr(pipeline,'predict_observations',unavailable)
    else:
        import mlflow
        def unavailable(*args):
            raise RuntimeError('required tracking failed')
        monkeypatch.setattr(mlflow,'set_tracking_uri',unavailable)
        monkeypatch.setattr(settings,'mlflow_required',True)
    with pytest.raises(RuntimeError,match='failed'):
        engine.run_training_job('FD001','Ridge')
    job = engine.store.list_training_jobs()[0]
    assert job['status']=='FAILED' and not job['promoted'] and job['previous_rmse'] is None
    assert (next((tmp_path/'training_artifacts').iterdir())/'bundle.joblib').is_file()


def test_unscored_forecast_cannot_return_invented_zero_costs():
    scheduler = FleetMaintenanceScheduler()
    with pytest.raises(ValueError,match="unavailable"):
        scheduler.simulate_fleet([profile()])
    with pytest.raises(ValueError,match="explicit"):
        scheduler.evaluate_comparison([profile()])
