"""Behavioral regressions for Trust/Value/Execution foundations; no field claims."""
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys
import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor
from flairguard.anomaly import StatisticalDeviationDetector, PersistenceFilter
from flairguard.evidence import digest, file_sha, load_protocol, write_json
from flairguard.features import add_causal_features
from flairguard.metrics import regression_metrics
from flairguard.phase_a import corrupt
from flairguard.policy_eval import score_ledger
from flairguard.quality import ACTIVE_SENSORS, TELEMETRY_CHANNELS, TelemetryQualityAuditor, QualityAssessment
from flairguard.replay import InferenceEngine, CausalReplay, prefix_features, simulate_episode
from flairguard.storage import WorkOrderStore, EventConflict, OutOfOrder, ConcurrentUpdate, finalize_ledger
from flairguard.triage import RiskAwareTriageAgent

PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('independent_phase_a_scorer',PROJECT/'scripts/07_score_phase_a.py')
scorer=importlib.util.module_from_spec(spec);spec.loader.exec_module(scorer)


def telemetry(cycle):
    return {key:float(100+i+cycle*.01) for i,key in enumerate(TELEMETRY_CHANNELS)}


def fixture_bundle(point=20.0):
    feat=prefix_features([{'cycle':1,**telemetry(1)}])
    model=DummyRegressor(strategy='constant',constant=point).fit(pd.DataFrame([feat]),[point])
    det=StatisticalDeviationDetector();det.fit(np.random.default_rng(42).normal(110,10,(100,14)));det.threshold=100.0
    return dict(model=model,features=list(feat),model_id='fixture-model',artifact_sha256='fixture-digest',
                rul_cap=125,protocol_hash='software-fixture-not-a-benchmark',min_history=2,
                detector=det,interval_q=10.0,quality_ranges={},
                quality_config=dict(bounds_sigma=6.0,stuck_window=3,stuck_atol=0.0))


def fixture_policy(kind='point',threshold=10):
    return dict(kind=kind,threshold=threshold,fixed_age=3,min_history=2,lead_time=2,
                review_delay=2,critical_threshold=5,stale_limit=2)


def record(store,cycle=1,**changes):
    args=dict(engine_id=1,cycle=cycle,severity='HIGH',action_type='WORK_ORDER_SCHEDULE_MAINTENANCE',
              predicted_rul=20.,uncertainty=None,anomaly_score=.3,persistence_count=0,
              decision_reason='fixture proposal',telemetry_snapshot={'sensor_2':100.})
    args.update(changes);return store.record_decision(**args)


def test_human_review_can_escalate_to_executable_critical(tmp_path):
    store=WorkOrderStore(tmp_path/'ledger.db')
    first=record(store,severity='ESCALATE_HUMAN',action_type='ESCALATE_HUMAN_CONFLICT',predicted_rul=70.)
    later=record(store,2,severity='CRITICAL',predicted_rul=5.)
    order=store.get_active_work_order(1)
    assert later['work_order_id']==first['work_order_id']
    assert later['status']=='ESCALATED' and order['priority']=='CRITICAL' and not order['review_required']
    assert order['action_type']=='WORK_ORDER_SCHEDULE_MAINTENANCE'
    assert not store.execute_due(1,6)
    assert store.execute_due(1,7)
    assert not store.execute_due(1,7)
    store.close()


def test_urgency_and_invalidity_are_both_retained(tmp_path):
    store=WorkOrderStore(tmp_path/'a.db');agent=RiskAwareTriageAgent(store)
    result=agent.evaluate(1,1,3.,None,.5,0,QualityAssessment(False,'MISSING_DATA',{}))
    order=store.get_active_work_order(1)
    assert result.priority=='CRITICAL' and result.review_required
    assert order['priority']=='CRITICAL' and order['review_required']
    assert not store.execute_due(1,2)
    store.close()


def test_exact_retry_after_closure_is_side_effect_free(tmp_path):
    store=WorkOrderStore(tmp_path/'a.db');first=record(store)
    store.close_work_order(first['work_order_id'])
    count=len(store.get_audit_trail());assert record(store)==first
    assert len(store.get_audit_trail())==count and len(store.get_all_work_orders())==1
    store.close()


def test_conflicting_retry_and_older_unknown_event_are_rejected(tmp_path):
    store=WorkOrderStore(tmp_path/'a.db');record(store,2)
    with pytest.raises(EventConflict):record(store,2,predicted_rul=19.)
    with pytest.raises(OutOfOrder):record(store,1)
    assert store.get_checkpoint(1)[0]==2
    store.close()


def test_same_numeric_engine_in_two_namespaces_does_not_collide(tmp_path):
    a=WorkOrderStore(tmp_path/'a.db','FD001/life1');b=WorkOrderStore(tmp_path/'a.db','FD002/life1')
    assert record(a)['work_order_id']!=record(b)['work_order_id']
    assert len(a.get_all_work_orders())==len(b.get_all_work_orders())==1
    a.close();b.close()


def test_concurrent_exact_retries_create_one_order_and_one_event(tmp_path):
    stores=[WorkOrderStore(tmp_path/'a.db') for _ in range(2)]
    with ThreadPoolExecutor(4) as pool:results=list(pool.map(lambda i:record(stores[i%2]),range(12)))
    assert all(r==results[0] for r in results)
    assert len(stores[0].get_all_work_orders())==len(stores[0].get_audit_trail())==1
    for store in stores:store.close()


def test_atomic_rollback_includes_event_order_and_checkpoint(tmp_path,monkeypatch):
    store=WorkOrderStore(tmp_path/'a.db')
    with monkeypatch.context() as m:
        def crash(*args,**kwargs):raise RuntimeError('injected process-boundary failure')
        m.setattr(store,'_audit',crash)
        with pytest.raises(RuntimeError):record(store)
    assert store.get_event(1,1) is None and store.get_checkpoint(1)==(None,{})
    assert store.get_all_work_orders()==[]
    assert record(store)['status']=='CREATED'
    store.close()


def test_stale_checkpoint_cannot_commit_a_different_cycle(tmp_path):
    store=WorkOrderStore(tmp_path/'a.db');record(store)
    with pytest.raises(ConcurrentUpdate):record(store,2,expected_previous_cycle=None)
    assert store.get_event(1,2) is None
    store.close()


def test_legacy_database_refused_without_mutation(tmp_path):
    db=tmp_path/'legacy.db'
    with sqlite3.connect(db) as c:c.execute('CREATE TABLE work_orders(id INTEGER)')
    before=file_sha(db)
    with pytest.raises(ValueError,match='protected'):WorkOrderStore(db)
    assert file_sha(db)==before and not Path(str(db)+'-wal').exists()


def test_missing_channel_never_nominal_and_next_valid_sample_recovers():
    q=TelemetryQualityAuditor();raw={s:100.0 for s in ACTIVE_SENSORS};bad=dict(raw);bad.pop('sensor_2')
    assert q.audit_row(1,1,bad).quality_code=='MISSING_DATA'
    assert q.audit_row(1,2,raw).is_valid


def test_gap_does_not_poison_all_following_samples():
    q=TelemetryQualityAuditor();raw={s:100.0 for s in ACTIVE_SENSORS}
    q.audit_row(1,1,raw)
    assert q.audit_row(1,3,raw).quality_code=='CYCLE_GAP'
    assert q.audit_row(1,4,raw).is_valid


def test_slow_changing_sensor_is_not_flatlined():
    q=TelemetryQualityAuditor(stuck_window=5)
    for cycle in range(1,6):
        raw={s:100+cycle for s in ACTIVE_SENSORS};raw['sensor_8']=2388+cycle*.001
        assert q.audit_row(1,cycle,raw).is_valid


def test_quality_state_survives_restart():
    first=TelemetryQualityAuditor(stuck_window=3);raw={s:100.0 for s in ACTIVE_SENSORS}
    first.audit_row(1,1,raw);first.audit_row(1,2,raw)
    second=TelemetryQualityAuditor(stuck_window=3);second.restore_state(1,first.state_for(1))
    assert second.audit_row(1,3,raw).quality_code=='STUCK_SENSOR'


def test_persistence_retries_gaps_and_order():
    filt=PersistenceFilter(3)
    assert filt.update(1,True,1)==filt.update(1,True,1)==1
    with pytest.raises(ValueError):filt.update(1,False,1)
    assert filt.update(1,True,3)==1
    with pytest.raises(ValueError):filt.update(1,True,2)


def test_raw_corruption_scales_by_fit_std_and_never_changes_settings_or_ids():
    frame=pd.DataFrame([dict(engine_id=1,cycle=t,**telemetry(t)) for t in range(1,8)])
    changed=corrupt(frame,dict(kind='drift',sensor='sensor_8',onset=3,duration=3,sigma=1),{'sensor_8':10},42)
    assert changed.loc[4,'sensor_8']-frame.loc[4,'sensor_8']==pytest.approx(10)
    pd.testing.assert_frame_equal(changed.drop(columns='sensor_8'),frame.drop(columns='sensor_8'))
    assert changed.loc[1,'sensor_8']==frame.loc[1,'sensor_8'] and changed.loc[5,'sensor_8']==frame.loc[5,'sensor_8']


def test_cycle_is_excluded_from_anomaly_score():
    infer=InferenceEngine(fixture_bundle());a,_=infer.observe(1,1,telemetry(1));b,_=infer.observe(1,100,telemetry(1))
    assert a['anomaly_score']==b['anomaly_score']
    assert a['features_hash']!=b['features_hash']


def test_prefix_features_equal_batch_features_and_future_cannot_change_them():
    history=[dict(engine_id=1,cycle=i,**telemetry(i)) for i in range(1,31)]
    batch,cols=add_causal_features(pd.DataFrame(history))
    for cycle in (1,5,20,30):
        feature=prefix_features(history[max(0,cycle-20):cycle])
        np.testing.assert_allclose([feature[k] for k in cols],batch.iloc[cycle-1][cols].to_numpy(dtype=float).round(10),atol=1e-10,rtol=0)
    changed=copy.deepcopy(history);changed[25]['sensor_8']=1e6
    assert prefix_features(history[:20])==prefix_features(changed[:20])


def test_label_keys_are_rejected_at_inference_boundary():
    with pytest.raises(ValueError,match='labels'):InferenceEngine(fixture_bundle()).observe(1,1,{**telemetry(1),'true_rul':5})


def test_restart_and_duplicate_replay_match_uninterrupted_state(tmp_path):
    bundle=fixture_bundle(50);policy=fixture_policy(threshold=5)
    whole=WorkOrderStore(tmp_path/'whole.db');a=CausalReplay(bundle,whole,policy)
    partial=WorkOrderStore(tmp_path/'partial.db');b=CausalReplay(bundle,partial,policy)
    for cycle in (1,2):
        assert a.consume(1,cycle,telemetry(cycle))==b.consume(1,cycle,telemetry(cycle))
    prior=b.consume(1,2,telemetry(2));partial.close()
    partial=WorkOrderStore(tmp_path/'partial.db');b=CausalReplay(bundle,partial,policy)
    assert b.consume(1,2,telemetry(2))==prior
    assert a.consume(1,3,telemetry(3))==b.consume(1,3,telemetry(3))
    assert whole.get_checkpoint(1)==partial.get_checkpoint(1)
    whole.close();partial.close()


def test_replay_context_cannot_silently_change_model(tmp_path):
    store=WorkOrderStore(tmp_path/'a.db');bundle=fixture_bundle();CausalReplay(bundle,store,fixture_policy())
    bundle['model_id']='other'
    with pytest.raises(EventConflict):CausalReplay(bundle,store,fixture_policy())
    store.close()


def test_pending_order_survives_a_separate_process_restart(tmp_path):
    """Reopen durable inference state and execute an order in another interpreter."""
    bundle=fixture_bundle(0);policy=fixture_policy()
    bundle_path=tmp_path/'bundle.joblib';joblib.dump(bundle,bundle_path)
    whole=WorkOrderStore(tmp_path/'whole.db','clean/point')
    partial=WorkOrderStore(tmp_path/'partial.db','clean/point')
    a=CausalReplay(bundle,whole,policy);b=CausalReplay(bundle,partial,policy)
    for cycle in (1,2):
        a.consume(1,cycle,telemetry(cycle));b.consume(1,cycle,telemetry(cycle))
    assert partial.get_active_work_order(1)['status']=='OPEN'
    partial.close()
    a.consume(1,3,telemetry(3));whole.execute_due(1,4)
    expected=whole.get_checkpoint(1);whole.close()
    program='''
import json, joblib, sys
sys.path.insert(0,sys.argv[1])
from flairguard.storage import WorkOrderStore
from flairguard.replay import CausalReplay
store=WorkOrderStore(sys.argv[2],'clean/point')
replay=CausalReplay(joblib.load(sys.argv[3]),store,json.loads(sys.argv[4]))
row=json.loads(sys.argv[5])
original=replay.consume(1,2,json.loads(sys.argv[6]))
assert original==json.loads(store.get_event(1,2)['result_json'])
replay.consume(1,3,row)
assert len(store.execute_due(1,4))==1
assert store.execute_due(1,4)==[]
store.close()
'''
    result=subprocess.run([sys.executable,'-B','-c',program,str(PROJECT),str(tmp_path/'partial.db'),
                           str(bundle_path),json.dumps(policy),json.dumps(telemetry(3)),
                           json.dumps(telemetry(2))],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    restarted=WorkOrderStore(tmp_path/'partial.db','clean/point')
    assert restarted.get_checkpoint(1)==expected
    assert restarted.get_active_work_order(1) is None
    restarted.close()
    costs=dict(planned=1.,failure=10.,unused_cycle=.05,inspection=.2)
    assert scorer.ledger_costs(tmp_path/'whole.db',{1:6},costs)==scorer.ledger_costs(tmp_path/'partial.db',{1:6},costs)


def test_finalized_ledger_is_immutable_under_repeated_independent_scoring(tmp_path):
    path=tmp_path/'sealed.db';store=WorkOrderStore(path,'clean/point')
    record(store);store.execute_due(1,6);store.close()
    finalize_ledger(path);before=file_sha(path)
    costs=dict(planned=1.,failure=10.,unused_cycle=.05,inspection=.2)
    assert scorer.ledger_costs(path,{1:10},costs)==scorer.ledger_costs(path,{1:10},costs)
    assert file_sha(path)==before
    assert not Path(str(path)+'-wal').exists() and not Path(str(path)+'-shm').exists()


@pytest.mark.parametrize('failure_cycle,expected_kind,expected_cost',[(4,'FAILURE',10.0),(6,'MAINTENANCE',1.1)])
def test_execution_boundary_and_reported_cost_agree_with_independent_scorer(tmp_path,failure_cycle,expected_kind,expected_cost):
    path=tmp_path/'a.db';store=WorkOrderStore(path,'clean/point')
    replay=CausalReplay(fixture_bundle(0),store,fixture_policy())
    observations=[dict(cycle=i,**telemetry(i)) for i in range(1,failure_cycle+1)]
    simulate_episode(replay,1,observations,failure_cycle)
    costs=dict(planned=1.,failure=10.,unused_cycle=.05,inspection=.2)
    actual=score_ledger(store,{1:failure_cycle},costs)[0]
    store.close()
    independent=scorer.ledger_costs(path,{1:failure_cycle},costs)[0]
    assert actual['outcome']==expected_kind and actual['total_cost']==pytest.approx(expected_cost)
    assert actual['total_cost']==independent['total_cost']


def test_review_completion_has_cost_but_does_not_yet_count_as_service(tmp_path):
    path=tmp_path/'a.db';store=WorkOrderStore(path,'clean/gate')
    record(store,severity='ESCALATE_HUMAN',action_type='ESCALATE_HUMAN_DATA_FAULT')
    store.execute_due(1,3,lead_time=5)  # Inspection only; service would be due at8.
    store.record_failure(1,7)
    costs=dict(planned=1.,failure=10.,unused_cycle=.05,inspection=.2)
    row=score_ledger(store,{1:7},costs)[0]
    assert row['planned']==0 and row['inspections']==1 and row['total_cost']==10.2
    store.close()
    assert scorer.ledger_costs(path,{1:7},costs)[0]['total_cost']==10.2


def test_human_closure_is_not_service_execution(tmp_path):
    store=WorkOrderStore(tmp_path/'a.db');r=record(store);store.close_work_order(r['work_order_id'])
    store.record_failure(1,10)
    row=score_ledger(store,{1:10},dict(planned=1,failure=10,unused_cycle=.05,inspection=.2))[0]
    assert row['failures']==1 and row['planned']==0
    store.close()


def test_metric_formula_asymmetry_full_precision_and_shape_guard():
    early=regression_metrics([20],[7]);late=regression_metrics([20],[33])
    assert early['phm08_score']==pytest.approx(math.expm1(1))
    assert late['phm08_score']>early['phm08_score']
    assert early['phm08_score']==scorer.metrics([(7,20)])['nasa_sum']
    assert regression_metrics([0],[1000])['phm08_score']>math.exp(50)
    with pytest.raises(ValueError):regression_metrics([[1],[2]],[1,2])
    with pytest.raises(ValueError):regression_metrics([1],[math.nan])


def test_protocol_partition_and_folds_cannot_overlap(tmp_path):
    p=json.loads((PROJECT/'configs/phase_a_fd001_v1.json').read_text())
    assert load_protocol(PROJECT/'configs/phase_a_fd001_v1.json')['partitions']==p['partitions']
    p['partitions']['calibration'][0]=p['partitions']['fit'][0]
    path=tmp_path/'bad.json';write_json(path,p)
    with pytest.raises(ValueError):load_protocol(path)


def test_evidence_json_never_overwrites_and_preserves_float_precision(tmp_path):
    path=tmp_path/'out.json';value=1.2345678901234567;write_json(path,{'x':value})
    before=file_sha(path)
    with pytest.raises(FileExistsError):write_json(path,{'x':2})
    assert file_sha(path)==before and json.loads(path.read_text())['x']==value


def test_independent_scorer_rejects_a_phantom_or_boundary_execution(tmp_path):
    store=WorkOrderStore(tmp_path/'a.db','clean/point');record(store);store.execute_due(1,6);store.close()
    # Declared failure at the same service cycle makes the persisted service invalid.
    with pytest.raises(ValueError,match='late execution'):
        scorer.ledger_costs(tmp_path/'a.db',{1:6},dict(planned=1,failure=10,unused_cycle=.05,inspection=.2))
