import copy
import json
import numpy as np
import pandas as pd
import pytest
from flairguard.phase_d.fleet import FleetController,evaluate_controller
from flairguard.phase_d.scorer import score
from flairguard.phase_d.protocol import freeze,load_predictor
from flairguard.phase_d.telemetry import prediction_stream,corrupt,decision_features
from flairguard.service.config import settings
from flairguard.data import read_trajectories

CONDITION=dict(name='fixture',bays=1,technicians=1,duration=4,lead=1,offset=0,fleet_limit=None)
COSTS=dict(failure=10.,service=1.,waste=.05,delay=.1,downtime=.05,inspection=.2)


def stream():
    return pd.DataFrame([dict(engine_id=eid,cycle=c,prediction=10.,available=True,stale_age=0,
                             missing_fraction=0.,model_id='fitted-test',model_sha256='a'*64)
                         for eid in [1,2] for c in range(20,41)])


def test_all_actual_predictor_and_preprocessing_lineages_are_disjoint():
    protocol=freeze(settings.root_dir)
    for ds,lineage in protocol['lineage'].items():
        assert not set(lineage['evaluation'])&set(lineage['predictor_fit']+lineage['preprocessing_fit'])
    assert len(protocol['lineage']['FD004']['evaluation'])==49
    assert 'Retrospective' in protocol['scope']


@pytest.mark.parametrize('death,completion',[(24,False),(25,False),(26,True)])
def test_phase_d_failure_service_math_and_independent_costs(death,completion):
    s=stream().query('engine_id==1')
    events,world=evaluate_controller(s,{1:death},CONDITION,'point')
    rows=score(events,world,CONDITION,COSTS)
    assert bool(rows[0]['completed']) is completion
    if completion:assert rows[0]['outcome_tick']==25
    assert all(e['order_id'] for e in events if e['kind'] in ['COMMIT','START','COMPLETE'])


def test_restart_roundtrip_and_capacity_invariants():
    normal,world=evaluate_controller(stream(),{1:40,2:41},CONDITION,'lookahead')
    restarted,_=evaluate_controller(stream(),{1:40,2:41},CONDITION,'lookahead',restart=True)
    assert normal==restarted
    rows=score(normal,world,CONDITION,COSTS)
    assert sum(r['completed'] for r in rows)==2
    forged=copy.deepcopy(normal)
    next(e for e in forged if e['kind']=='START')['tick']=20
    with pytest.raises(AssertionError):score(forged,world,CONDITION,COSTS)


def test_future_labels_cannot_enter_or_change_unobserved_controller_decisions():
    controller=FleetController([1,2],'point',CONDITION)
    controller.step(20,stream().query('cycle==20').to_dict('records'))
    same=FleetController.restore(json.loads(json.dumps(controller.checkpoint())))
    controller.step(21,stream().query('cycle==21').to_dict('records'))
    same.step(21,stream().query('cycle==21').to_dict('records'))
    assert controller.state['events']==same.state['events']
    with pytest.raises(ValueError,match='labels'):
        same.step(22,[dict(engine_id=1,cycle=22,prediction=4.,true_rul=1)])
    with pytest.raises(ValueError,match='labels'):
        decision_features(stream().assign(true_rul=1))


def test_real_corruption_recovery_is_prefix_causal_and_raw_is_preserved():
    bundle,_,_=load_predictor(settings.root_dir,'FD002')
    raw=read_trajectories(settings.data_dir/'train_FD002.txt')
    raw=raw.loc[raw.engine_id==1].iloc[:100].reset_index(drop=True)
    original=raw.copy(deep=True)
    case=dict(name='missing',kind='missing',onset=45,duration=5,channels=['sensor_8'])
    changed,manifest=corrupt(raw,case,42)
    assert manifest[0]['original_hash']!=manifest[0]['modified_hash']
    pd.testing.assert_frame_equal(raw,original)
    for strategy in ['abstain','bounded_last','forward_fill','regime_impute','decision_fallback']:
        full=prediction_stream(bundle,changed,strategy)
        prefix=prediction_stream(bundle,changed.iloc[:55].copy(),strategy)
        np.testing.assert_allclose(full.prediction.iloc[:55],prefix.prediction,equal_nan=True,atol=1e-10,rtol=0)
    assert not prediction_stream(bundle,changed,'abstain').loc[45:49,'available'].any()
    assert prediction_stream(bundle,changed,'forward_fill').loc[45:49,'available'].all()


def test_no_maintenance_and_review_terminal_coverage():
    s=stream();s['prediction']=np.nan;s['available']=False;s['stale_age']=30
    events,world=evaluate_controller(s,{1:40,2:41},CONDITION,'point',recovery='decision_fallback')
    rows=score(events,world,CONDITION,COSTS)
    assert len(rows)==2 and sum(r['inspections'] for r in rows)==2
    events,world=evaluate_controller(stream(),{1:40,2:41},CONDITION,'none')
    assert sum(r['failures'] for r in score(events,world,CONDITION,COSTS))==2


def test_risk_history_cannot_cross_corruption_scenarios():
    from flairguard.phase_d.telemetry import decision_features
    a=pd.DataFrame(dict(engine_id=[1]*8,cycle=range(20,28),prediction=range(40,32,-1),
        available=True,stale_age=0,missing_fraction=0.,regime=0,scenario='clean'))
    b=a.assign(scenario='missing',prediction=100.)
    expected=decision_features(b).reset_index(drop=True)
    actual=decision_features(pd.concat([a,b],ignore_index=True)).iloc[len(a):].reset_index(drop=True)
    pd.testing.assert_frame_equal(expected,actual)


def test_future_failure_labels_only_change_observable_terminal_notifications():
    first,_=evaluate_controller(stream(),{1:40,2:41},CONDITION,'point')
    changed,_=evaluate_controller(stream(),{1:140,2:141},CONDITION,'point')
    assert [e for e in first if e['tick']<40]==[e for e in changed if e['tick']<40]


def test_missing_packet_wire_format_and_observed_prefix_export():
    from fastapi.testclient import TestClient
    from flairguard.service.app import create_app
    with TestClient(create_app(),headers={'X-API-Key':settings.api_key}) as client:
        session=client.post('/api/v1/replay/start',json=dict(dataset='FD002',engine_id=15,policy='quality_gate')).json()
        sid=session['session_id']
        assert client.post(f'/api/v1/replay/{sid}/step',json={'step_count':20}).status_code==200
        assert client.post(f'/api/v1/replay/{sid}/inject-fault',json=dict(fault_type='missing_data',channel='sensor_11',start_cycle=21,duration=3)).status_code==200
        response=client.post(f'/api/v1/replay/{sid}/step',json={'step_count':1})
        assert response.status_code==200
        assert response.json()['last_evidence']['telemetry']['sensor_11'] is None
        assert response.json()['last_evidence']['usable'] is False
        exported=client.get(f'/api/v1/replay/{sid}/export').json()
        assert max(e['cycle'] for e in exported['events'])==exported['current_cycle']==21
        assert exported['model_release'] and exported['namespace']
        assert client.get('/api/v1/models/history').json()


def test_missing_direct_prediction_is_unavailable_instead_of_error():
    from fastapi.testclient import TestClient
    from flairguard.service.app import create_app
    with TestClient(create_app(),headers={'X-API-Key':settings.api_key}) as client:
        response=client.post('/api/v1/predict',json=dict(dataset='FD002',engine_id=1,cycle=20,
            settings=[0.,0.,100.],sensors={f'sensor_{i}':None for i in range(1,22)}))
        assert response.status_code==200
        assert response.json()['predicted_rul'] is None and not response.json()['usable']


def test_phase_d_api_evidence_is_hash_bound():
    from fastapi.testclient import TestClient
    from flairguard.service.app import create_app
    with TestClient(create_app()) as client:
        response=client.get('/api/v1/reliability/summary')
        assert response.status_code==200
        assert response.json()['execution']['engine_episodes']==17822
        ledger=client.get('/api/v1/reliability/ledger',params={'run_id':'FD004-clean-abstain-reference-point'})
        assert ledger.status_code==200 and ledger.json()['events']
        assert client.get('/api/v1/reliability/ledger',params={'run_id':'../outside'}).status_code==422


def test_concurrent_replay_advances_do_not_skip_committed_cycles():
    from concurrent.futures import ThreadPoolExecutor
    from flairguard.service.replay_manager import replay_manager
    session=replay_manager.create_session('FD001',15)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(session.step,10) for _ in range(2)]
        for future in futures:future.result()
    assert session.current_index==20
    with session.store._get_connection() as c:
        cycles=[r[0] for r in c.execute('SELECT cycle FROM decision_events WHERE namespace=? ORDER BY cycle',(session.namespace,))]
    assert cycles==list(range(1,21))
