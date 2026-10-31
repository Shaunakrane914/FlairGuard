"""Behavioral and differential tests for the FD002 scientific extension."""
import copy
import importlib.util
import json
import math
from pathlib import Path
from contextlib import closing
import sqlite3
import joblib
import numpy as np
import pandas as pd
import pytest
from flairguard.regimes import RegimeFeatures, RegimeModel, corrupt_measurements, selector_inputs
from flairguard.phase_b import load_protocol, policy, predict_stream, plan_power
from flairguard.decision_experiments import propose, next_state, fast_schedule, schedule_cost, EvidenceReplay, execute_episode
from flairguard.quality import TELEMETRY_CHANNELS, ACTIVE_SENSORS
from flairguard.storage import WorkOrderStore, OutOfOrder, EventConflict, finalize_ledger

PROJECT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('independent_b',PROJECT/'scripts/10_score_phase_b.py')
scorer=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(scorer)


@pytest.fixture
def raw():
    rows=[]
    for engine in range(1,7):
        for cycle in range(1,81):
            regime=cycle%6
            row=dict(engine_id=engine,cycle=cycle,setting_1=100.*regime,setting_2=.1*regime,setting_3=20.+regime)
            row.update({f'sensor_{j}':100.+regime*(j+1)+cycle*.001*j+engine*.002 for j in range(1,22)})
            rows.append(row)
    return pd.DataFrame(rows)


def protocol():return load_protocol(PROJECT/'configs/phase_b_fd002_v1.json')


def evidence(seed=0):
    rng=np.random.default_rng(seed);rows=[]
    for cycle in range(1,81):
        available=not 25<=cycle<=30
        prediction=max(0,80-cycle+float(rng.normal(0,10))) if available else None
        rows.append(dict(engine_id=1,cycle=cycle,prediction=prediction,available=available,
                         risk_score=float(rng.random()*4) if available else None,
                         quality_score=float(rng.random()*4) if available else None))
    return rows


def test_five_roles_and_folds_are_disjoint(tmp_path):
    p=protocol();assert [len(v) for v in p['partitions'].values()]==[100,30,30,20,80]
    p['partitions']['selector_fit'][0]=p['partitions']['evaluation'][0]
    path=tmp_path/'bad.json';path.write_text(json.dumps(p))
    with pytest.raises(ValueError,match='leakage'):load_protocol(path)


def test_fit_only_reference_is_frozen_and_clusters_have_stable_order(raw):
    features=RegimeFeatures(seed=42).fit(raw);before=features.means_.copy()
    changed=raw.copy();changed.loc[changed.cycle>60,'sensor_8']+=1000
    features.transform(changed)
    np.testing.assert_array_equal(features.means_,before)
    assert features.fit_engines_==list(range(1,7))
    assert list(features.centers_[:,0])==sorted(features.centers_[:,0])


def test_normalize_each_observation_before_rolling_across_regimes(raw):
    transformer=RegimeFeatures().fit(raw);X,_=transformer.transform(raw)
    last=raw[raw.engine_id==1].iloc[:20];labels,_=transformer.assign(last)
    j=ACTIVE_SENSORS.index('sensor_8');normalized=(last.sensor_8.to_numpy()-transformer.means_[labels,j])/transformer.scales_[labels,j]
    assert X.iloc[19]['sensor_8_mean_5']==pytest.approx(normalized[-5:].mean(),abs=1e-9)


def test_features_are_prefix_causal_and_future_invariant(raw):
    transformer=RegimeFeatures().fit(raw);full,diag=transformer.transform(raw)
    prefix=raw[(raw.engine_id==1)&(raw.cycle<=40)];short,small=transformer.transform(prefix)
    pd.testing.assert_series_equal(full.loc[prefix.index[-1]],short.iloc[-1])
    pd.testing.assert_series_equal(diag.loc[prefix.index[-1]],small.iloc[-1])
    changed=raw.copy();changed.loc[(changed.engine_id==1)&(changed.cycle>40),'sensor_8']=1e6
    later,_=transformer.transform(changed)
    pd.testing.assert_frame_equal(full.loc[prefix.index],later.loc[prefix.index])


def test_missing_history_rebuilds_without_future_fill(raw):
    transformer=RegimeFeatures().fit(raw);bad=raw[raw.engine_id==1].copy();bad.loc[bad.cycle.between(30,34),'sensor_8']=np.nan
    _,diagnostic=transformer.transform(bad)
    assert diagnostic.loc[bad.cycle==34,'history_length'].item()==0
    assert diagnostic.loc[bad.cycle==35,'history_length'].item()==1
    assert diagnostic.loc[bad.cycle==54,'history_length'].item()==20


def test_target_and_lifetime_cannot_enter_feature_boundary(raw):
    with pytest.raises(ValueError,match='labels'):RegimeFeatures().fit(raw.assign(true_rul=10))


def test_corruption_is_local_regime_scaled_and_preserves_settings_and_identity(raw):
    reference=RegimeFeatures().fit(raw);scenario=dict(kind='drift',sensors=['sensor_8'],sigma=-3,onset=40,duration=10)
    changed=corrupt_measurements(raw,scenario,reference,42)
    pd.testing.assert_frame_equal(raw.drop(columns='sensor_8'),changed.drop(columns='sensor_8'))
    labels,_=reference.assign(raw);position=raw.index[raw.engine_id.eq(1)&raw.cycle.eq(49)][0];j=ACTIVE_SENSORS.index('sensor_8')
    assert changed.loc[position,'sensor_8']-raw.loc[position,'sensor_8']==pytest.approx(-3*reference.scales_[labels[position],j])
    pd.testing.assert_series_equal(raw.loc[raw.cycle==50,'sensor_8'],changed.loc[changed.cycle==50,'sensor_8'])


def test_selector_inputs_never_include_target_interval_or_engine_id():
    data=pd.DataFrame([dict(cycle=50,prediction=20,disagreement=2,support_max=3,support_mean=1,innovation_mean=.5,
                           setting_distance=.01,history_length=20,missing_fraction=0,flatline=False,regime=1,
                           engine_id=123,true_rul=1,upper=999,lower=0)])
    assert not {'engine_id','true_rul','upper','lower'}&set(selector_inputs(data))


@pytest.mark.parametrize('kind',['none','fixed','point','quality_gate','quality_decision','learned_gate'])
def test_fast_development_scheduler_matches_transactional_execution(kind):
    for seed in range(8):
        rows=evidence(seed);pol=policy(protocol(),kind,threshold=20,stale=5,risk_threshold=2,fixed_age=50);pol['min_history']=2
        store=WorkOrderStore(':memory:',f'test/{kind}');replay=EvidenceReplay(store,pol,'fixture','fixture-protocol')
        telemetry=[{k:float(i+j) for j,k in enumerate(TELEMETRY_CHANNELS)} for i in range(len(rows))]
        actual=execute_episode(replay,1,rows,telemetry,80)
        assert actual==fast_schedule(rows,80,pol)
        store.close()


def test_decision_aware_rejection_does_not_immediately_replace_far_from_action():
    row=dict(cycle=50,prediction=100,available=True,risk_score=10,quality_score=10)
    learned=policy(protocol(),'learned_gate',threshold=20,stale=0,risk_threshold=2)
    broad={**learned,'kind':'quality_gate'}
    assert propose(row,{},learned).action_type=='MONITOR'
    assert propose(row,{},broad).review_required
    row['prediction']=3
    result=propose(row,{},learned);assert result.priority=='CRITICAL' and result.review_required


def test_unsupported_missing_evidence_has_bounded_fallback():
    pol=policy(protocol(),'learned_gate',threshold=20,stale=5,risk_threshold=2)
    row=dict(cycle=46,prediction=None,available=False,risk_score=None,quality_score=None)
    assert propose(row,dict(last_valid=dict(cycle=40,prediction=80)),pol).review_required


def test_replay_retry_and_out_of_order_preserve_committed_state():
    store=WorkOrderStore(':memory:','test/point');replay=EvidenceReplay(store,policy(protocol(),'point'),'fixture','fixture')
    row=evidence()[20];payload={k:1. for k in TELEMETRY_CHANNELS}
    original=replay.consume(1,row,payload);checkpoint=store.get_checkpoint(1)
    assert replay.consume(1,row,payload)==original and store.get_checkpoint(1)==checkpoint
    with pytest.raises(EventConflict):replay.consume(1,{**row,'prediction':3},payload)
    with pytest.raises(OutOfOrder):replay.consume(1,{**row,'cycle':20},payload)
    with pytest.raises(ValueError,match='labels'):replay.consume(1,{**row,'true_rul':3},payload)
    store.close()


def test_execution_boundary_and_snapshot_are_real(tmp_path):
    pol=policy(protocol(),'point',threshold=20,stale=0);pol['min_history']=2
    rows=[dict(engine_id=1,cycle=t,prediction=0,available=True,risk_score=0,quality_score=0) for t in range(1,8)]
    store=WorkOrderStore(':memory:','test/point');replay=EvidenceReplay(store,pol,'fixture','fixture')
    actual=execute_episode(replay,1,rows,[{k:1. for k in TELEMETRY_CHANNELS}]*7,7)
    assert actual['outcome']=='FAILURE' # Service due at2+5=7 loses to failure.
    target=tmp_path/'snapshot.db'
    with closing(sqlite3.connect(target)) as dest:store.conn.backup(dest)
    store.close();finalize_ledger(target)
    with closing(sqlite3.connect(target)) as conn:assert conn.execute('SELECT kind FROM episode_outcomes').fetchone()[0]=='FAILURE'


def test_fast_cost_cannot_count_late_service():
    with pytest.raises(ValueError):schedule_cost(dict(outcome='MAINTENANCE',outcome_cycle=10,inspection_cycles=[]),10,protocol()['costs'])


def test_exact_paired_harm_bound_does_not_treat_scenarios_as_engines():
    assert scorer.harm_upper(0,80)==pytest.approx(0.0367541977799823)
    assert scorer.harm_upper(0,20)>.05
    assert scorer.harm_upper(1,80)>.05


def test_zero_development_differences_cannot_claim_perfect_power():
    result=plan_power([0.]*30,[2.]*30,80,.05)
    assert result['approximate_power_for_five_percent'] is None and not result['power_adequate']
    assert result['mde_80_percent'] is None and result['status'].startswith('NOT_ESTIMABLE')


def test_saved_regime_model_and_streaming_prefix_match(raw,tmp_path):
    from sklearn.dummy import DummyRegressor
    p=protocol();models={n:RegimeModel(n,p).fit(raw,80-raw.cycle.to_numpy()) for n in ('GlobalLightGBM','RegimeLightGBM')}
    first=predict_stream(raw,models,'RegimeLightGBM',p)
    selector=DummyRegressor(strategy='constant',constant=1).fit(selector_inputs(first[first.available]),np.ones(first.available.sum()))
    full=predict_stream(raw,models,'RegimeLightGBM',p,selector)
    path=tmp_path/'model.joblib';joblib.dump(models,path);loaded=joblib.load(path)
    after=predict_stream(raw,loaded,'RegimeLightGBM',p,selector)
    pd.testing.assert_frame_equal(full,after)
    prefix=raw[(raw.engine_id==1)&(raw.cycle<=40)]
    short=predict_stream(prefix,loaded,'RegimeLightGBM',p,selector)
    pd.testing.assert_series_equal(full.loc[prefix.index[-1]],short.iloc[-1])
    assert full[full.cycle<20].prediction.isna().all()


def test_independent_trust_statistics_keep_the_engine_as_sampling_unit():
    p=copy.deepcopy(protocol());ids=p['partitions']['evaluation'];p['scenarios']=[dict(name='clean'),dict(name='noise')]
    p['endpoint_cycles']={str(e):40 for e in ids};p['bootstrap_replicates']=40;p['random_rejection_replicates']=20
    rows=[];truth={}
    for i,e in enumerate(ids):
        truth[e,40]=10;loss=100 if i>=72 else 1
        rows.append(dict(engine_id=str(e),cycle='40',prediction=str(10+loss),risk_score=str(loss),quality_score=str(loss),
                         lower='0',upper='200',regime=str(i%6),available='True'))
    thresholds={kind:{str(b):2. for b in p['budgets']} for kind in ('learned_gate','quality_gate')}
    def metric(pairs):
        return dict(n=len(pairs),mae=sum(abs(a-b) for a,b in pairs)/len(pairs) if pairs else None)
    report=scorer.trust_report(dict(clean=rows,noise=copy.deepcopy(rows)),truth,p,thresholds,metric)
    assert report['primary']['n_independent_engines']==80
    assert report['primary']['accepted_minus_expected_random_mae']<0
    assert report['primary']['engine_bootstrap_95'][1]<0
    assert report['primary']['low_rul_automation_coverage']==.9
