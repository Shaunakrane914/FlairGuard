"""Protocol-locked FD001 evidence run. No official test reads or production claims."""
from pathlib import Path
from datetime import datetime, timezone
import copy
import importlib.metadata
import json
import math
import platform
import shutil
import subprocess
import sys
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from threadpoolctl import threadpool_limits
from .data import read_trajectories, add_train_rul
from .features import add_causal_features
from .metrics import regression_metrics
from .models import get_model_candidates
from .anomaly import StatisticalDeviationDetector, PCAReconstructionDetector, IsolationForestDetector, PersistenceFilter
from .quality import TelemetryQualityAuditor, TELEMETRY_CHANNELS, ACTIVE_SENSORS
from .evidence import load_protocol, file_sha, digest, write_json
from .replay import InferenceEngine, CausalReplay, simulate_episode
from .storage import WorkOrderStore, finalize_ledger
from .policy_eval import score_ledger

PROJECT = Path(__file__).resolve().parents[1]


def csv(path, frame):
    frame.to_csv(path,index=False,float_format="%.17g",mode="x",lineterminator="\n")


def candidates(seed):
    result = get_model_candidates(seed)
    for model in result.values():
        if 'n_jobs' in model.get_params():
            model.set_params(n_jobs=2)
    result['AgeRidge'] = Pipeline([('age',ColumnTransformer([('cycle','passthrough',['cycle'])])),
                                   ('regressor',Ridge(alpha=100.0))])
    result['Constant'] = DummyRegressor(strategy='mean')
    return result


def endpoints(frame, protocol):
    return frame[frame.apply(lambda r: int(r['cycle']) == protocol['endpoint_cycles'][str(int(r['engine_id']))],axis=1)]


def policy_config(protocol, kind, threshold, fixed_age):
    return dict(kind=kind,threshold=int(threshold),fixed_age=int(fixed_age),
                min_history=protocol['min_history'],**{k:protocol['policy'][k] for k in
                ('lead_time','review_delay','critical_threshold','stale_limit')})


def tune_simple_policies(oof, fit_truth, p):
    """OOF fit-engine predictions only. Identical positive service lead time."""
    merged = oof.merge(fit_truth[['engine_id','cycle','true_rul']],on=['engine_id','cycle'],validate='one_to_one')
    scores = []
    costs = p['costs']
    for kind, grid in [('point',p['policy']['threshold_grid']),('fixed',p['policy']['fixed_age_grid'])]:
        for value in grid:
            total = 0.0
            failures = 0
            for engine, g in merged.groupby('engine_id'):
                T = int(g.cycle.max())
                eligible = g[g.cycle >= p['min_history']]
                trigger = (eligible[eligible.prediction <= value].cycle.min() if kind=='point' else value)
                service = trigger+p['policy']['lead_time']
                if pd.isna(service) or service >= T:
                    total += costs['failure'];failures += 1
                else:
                    total += costs['planned']+costs['unused_cycle']*(T-service)
            scores.append(dict(kind=kind,parameter=value,total_cost=total,failures=failures))
    selected = {}
    for kind in ('point','fixed'):
        selected[kind] = min((r for r in scores if r['kind']==kind),key=lambda r:(r['total_cost'],r['failures'],r['parameter']))['parameter']
    return selected,scores


def corrupt(history, scenario, sensor_stds, seed):
    """Raw measurement experiment; IDs/settings/failure times remain unchanged."""
    out = history.copy(deep=True)
    if scenario['kind']=='clean':
        return out
    sensor = scenario['sensor']
    mask = out.cycle.between(scenario['onset'],scenario['onset']+scenario['duration']-1)
    indices = out.index[mask]
    if scenario['kind']=='missing':
        out.loc[mask,sensor] = np.nan
    elif scenario['kind']=='stuck':
        previous = out[out.cycle < scenario['onset']]
        if previous.empty:
            raise ValueError('Stuck injection requires an available previous measurement')
        out.loc[mask,sensor] = previous[sensor].iloc[-1]
    elif scenario['kind']=='noise':
        rng = np.random.default_rng(seed+int(out.engine_id.iloc[0]))
        out.loc[mask,sensor] += rng.normal(0,scenario['sigma']*sensor_stds[sensor],len(indices))
    elif scenario['kind']=='drift':
        out.loc[mask,sensor] += np.arange(1,len(indices)+1)/scenario['duration']*scenario['sigma']*sensor_stds[sensor]
    else:
        raise ValueError('Unknown declared scenario')
    return out


def anomaly_evaluation(train, p, run):
    roles = p['partitions'];nominal = train[train.cycle <= p['anomaly']['nominal_cutoff']]
    fit = nominal[nominal.engine_id.isin(roles['fit'])]
    cal = nominal[nominal.engine_id.isin(roles['calibration'])]
    evaluation = nominal[nominal.engine_id.isin(roles['evaluation'])]
    detectors = {'Statistical_Deviation':StatisticalDeviationDetector(),
                 'PCA_Reconstruction':PCAReconstructionDetector(5),
                 'Isolation_Forest':IsolationForestDetector(100,p['seed'])}
    rows = []; report = {};frozen_std = fit[ACTIVE_SENSORS].std(ddof=0).to_dict()
    for name, detector in detectors.items():
        detector.fit(fit[ACTIVE_SENSORS].to_numpy())
        detector.calibrate_threshold(cal[ACTIVE_SENSORS].to_numpy(),p['anomaly']['target_far'])
        case_report = {}
        cases = [('clean',evaluation)]
        for kind in ('noise','drift','stuck','missing'):
            for strength in ([0.5,1.0,3.0] if kind in ('noise','drift') else [1.0]):
                sc = dict(kind=kind,sensor='sensor_8',onset=6,duration=10,sigma=strength)
                changed = pd.concat([corrupt(g,sc,frozen_std,p['seed']) for _,g in evaluation.groupby('engine_id')])
                cases.append((f'{kind}_{strength}',changed))
        for case, frame in cases:
            X = frame[ACTIVE_SENSORS].to_numpy()
            good = np.isfinite(X).all(axis=1)
            scores = np.full(len(X),np.nan)
            scores[good] = detector.compute_raw_score(X[good])
            flags = np.isfinite(scores) & (scores >= detector.threshold)
            for i, (_, r) in enumerate(frame.iterrows()):
                rows.append(dict(detector=name,case=case,engine_id=int(r.engine_id),cycle=int(r.cycle),
                                 score=scores[i],threshold=detector.threshold,flag=bool(flags[i]),
                                 score_available=bool(good[i]),synthetic_event=case!='clean' and 6 <= r.cycle <= 15))
            event = frame.cycle.between(6,15).to_numpy() if case!='clean' else np.zeros(len(frame),dtype=bool)
            case_report[case] = dict(flagged_cycle_fraction=float(flags.mean()),score_availability=float(good.mean()),
                                     synthetic_event_detection_fraction=float(flags[event & good].mean()) if (event & good).any() else None,
                                     event_score_availability=float(good[event].mean()) if event.any() else None)
        report[name] = dict(threshold=detector.threshold,evaluation=case_report)
        joblib.dump(detector,run/'models'/f'anomaly_{name}.joblib')
    csv(run/'anomaly_scores.csv',pd.DataFrame(rows))
    persistence = []
    production = pd.DataFrame(rows).query("detector == 'Statistical_Deviation'")
    for (case,engine), g in production.groupby(['case','engine_id']):
        for k in (1,3,5,8):
            filt=PersistenceFilter(k);first=None;episodes=0;active=False
            for row in g.itertuples():
                count=filt.update(int(engine),bool(row.flag),int(row.cycle));alarmed=count>=k
                episodes += int(alarmed and not active);active=alarmed
                if row.synthetic_event and alarmed and first is None:first=int(row.cycle)
            persistence.append(dict(case=case,engine_id=int(engine),k=k,episodes=episodes,
                                    event_detected=first is not None,delay_cycles=first-6 if first is not None else None))
    csv(run/'anomaly_episodes.csv',pd.DataFrame(persistence))
    write_json(run/'anomaly_report.json',dict(results=report,fit_engines=roles['fit'],
                calibration_engines=roles['calibration'],evaluation_engines=roles['evaluation'],
                feature_schema=ACTIVE_SENSORS,scope='Assumed nominal reference and synthetic measurement events; no physical fault accuracy',
                persistence='Sensitivity only; k=3 frozen a priori, no optimality claim'))
    return detectors[p['anomaly']['production_detector']],frozen_std


def run_phase_a(protocol_path, data_dir, run_dir):
    run = Path(run_dir);run.mkdir(parents=True,exist_ok=False)
    (run/'models').mkdir();(run/'predictions').mkdir();(run/'oof').mkdir()
    train_file = Path(data_dir)/'train_FD001.txt'
    p = load_protocol(protocol_path,train_file);protocol_hash=digest(p)
    source_paths = sorted(list((PROJECT/'flairguard').glob('*.py'))+list((PROJECT/'scripts').glob('*.py'))+
                          list((PROJECT/'tests').glob('*.py'))+[PROJECT/'configs/phase_a_fd001_v1.json',PROJECT/'requirements-phase-a.lock.txt'])
    source_hashes = {}
    for path in source_paths:
        relative=path.relative_to(PROJECT);source_hashes[relative.as_posix()]=file_sha(path)
        destination=run/'source'/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
    environment = dict(python=sys.version,platform=platform.platform(),packages={
        name:importlib.metadata.version(name) for name in ('numpy','pandas','scikit-learn','scipy','lightgbm','joblib','threadpoolctl','pytest')})
    write_json(run/'run_plan.json',dict(protocol_hash=protocol_hash,protocol=p,source_hashes=source_hashes,
                                     environment=environment,started_utc=datetime.now(timezone.utc).isoformat(),
                                     scope='FD001 training pool only; prospective pilot following historical exploration'))
    write_json(run/'protocol.json',p)
    train=read_trajectories(train_file)
    labeled=add_train_rul(train)
    frame,features=add_causal_features(train)
    frame[features]=frame[features].round(p['feature_round_decimals'])
    frame['role']=frame.engine_id.map({engine:role for role,ids in p['partitions'].items() for engine in ids})
    truth=labeled[['engine_id','cycle','true_rul']].copy()
    csv(run/'labels_evaluator_only.csv',truth)
    endpoint_rows=[]
    for engine,g in train.groupby('engine_id'):
        cutoff=p['endpoint_cycles'][str(engine)]
        endpoint_rows.append(dict(engine_id=int(engine),cutoff=cutoff,role=frame.loc[g.index[0],'role'],
                                  status='AVAILABLE' if cutoff <= int(g.cycle.max()) else 'FAILED_BEFORE_CUTOFF'))
    csv(run/'endpoint_population.csv',pd.DataFrame(endpoint_rows))
    fits=frame[frame.role=='fit'];y=truth.set_index(['engine_id','cycle']).true_rul
    fit_truth=truth[truth.engine_id.isin(p['partitions']['fit'])]
    selections={};oofs={};folds_metadata=[]
    with threadpool_limits(limits=2):
        for name in candidates(p['seed']):
            print('Fit-only CV:',name,flush=True)
            parts=[]
            for fold, val_ids in enumerate(p['cv_folds']):
                f=fits[~fits.engine_id.isin(val_ids)];v=fits[fits.engine_id.isin(val_ids)]
                model=candidates(p['seed'])[name]
                yt=y.loc[list(zip(f.engine_id,f.cycle))].to_numpy().clip(0,p['rul_cap'])
                model.fit(f[features],yt)
                raw=model.predict(v[features]);prediction=np.clip(raw,0,p['rul_cap'])
                part=v[['engine_id','cycle']].copy();part['prediction']=prediction;part['raw_prediction']=raw;part['fold']=fold
                parts.append(part)
                if name=='Ridge':
                    folds_metadata.append(dict(fold=fold,fit_engines=sorted(map(int,f.engine_id.unique())),validation_engines=val_ids))
            oof=pd.concat(parts).sort_values(['engine_id','cycle']);oofs[name]=oof
            endpoint=endpoints(oof,p).merge(truth,on=['engine_id','cycle'],validate='one_to_one')
            selections[name]=regression_metrics(endpoint.true_rul,endpoint.prediction)
            csv(run/'oof'/f'{name}.csv',oof)
        # No evaluation or calibration predictions enter this choice.
        selected=min(selections,key=lambda name:(selections[name]['rmse_cycles'],list(candidates(p['seed'])).index(name)))
        tuned,policy_tuning=tune_simple_policies(oofs[selected],fit_truth,p)
        write_json(run/'selection.json',dict(model=selected,selection_metrics=selections,folds=folds_metadata,
                    chosen_policy_parameters=tuned,policy_tuning=policy_tuning,
                    selection_scope='fit-only OOF frozen endpoints; policy tuning uses fit-only OOF full causal cycles'))
        fitted={};metadata={}
        for name,model in candidates(p['seed']).items():
            model.fit(fits[features],y.loc[list(zip(fits.engine_id,fits.cycle))].to_numpy().clip(0,p['rul_cap']))
            model_id=digest(dict(name=name,protocol_hash=protocol_hash,source_hashes=source_hashes))
            package=dict(model=model,model_id=model_id,features=features,rul_cap=p['rul_cap'],
                         fit_engines=p['partitions']['fit'],protocol_hash=protocol_hash)
            path=run/'models'/f'{name}.joblib';joblib.dump(package,path)
            loaded=joblib.load(path)
            raw=model.predict(frame[features]);reload_raw=loaded['model'].predict(frame[features])
            np.testing.assert_allclose(raw,reload_raw,rtol=0,atol=p['acceptance']['model_reproduction_atol'])
            predictions=frame[['engine_id','cycle','role']].copy();predictions['raw_prediction']=raw
            predictions['prediction']=np.clip(raw,0,p['rul_cap']);predictions['model_id']=model_id
            csv(run/'predictions'/f'{name}.csv',predictions)
            metadata[name]=dict(model_id=model_id,sha256=file_sha(path),fit_engines=p['partitions']['fit'],
                                parameters={k:(v if isinstance(v,(str,int,float,bool,type(None))) else repr(v)) for k,v in model.get_params(deep=True).items()},roundtrip_max_abs=float(np.max(np.abs(raw-reload_raw))))
            fitted[name]=package
        bundle=fitted[selected]
        cal=pd.read_csv(run/'predictions'/f'{selected}.csv',float_precision='round_trip')
        cal=endpoints(cal[cal.role=='calibration'],p).merge(truth,on=['engine_id','cycle'],validate='one_to_one')
        n=len(cal);rank=math.ceil((n+1)*(1-p['interval']['alpha']))
        if rank > n:raise ValueError('Insufficient calibration engines for requested interval')
        q=float(np.sort(np.abs(cal.true_rul-cal.prediction))[rank-1])
        write_json(run/'interval_calibration.json',dict(n_engines=n,rank=rank,q=q,alpha=p['interval']['alpha'],
                     engine_ids=list(map(int,cal.engine_id)),scope=p['interval']['scope']))
        detector,sensor_stds=anomaly_evaluation(train,p,run)
        auditor=TelemetryQualityAuditor(**{k:p['quality'][k] for k in ('bounds_sigma','stuck_window','stuck_atol')})
        auditor.fit_reference_ranges(train[train.engine_id.isin(p['partitions']['fit'])])
        bundle.update(interval_q=q,detector=detector,quality_ranges=auditor.nominal_ranges,
                      quality_config={k:p['quality'][k] for k in ('bounds_sigma','stuck_window','stuck_atol')},
                      min_history=p['min_history'],calibration_engines=p['partitions']['calibration'],corruption_sensor_stds=sensor_stds)
        joblib.dump(bundle,run/'models/bundle.joblib');bundle=joblib.load(run/'models/bundle.joblib')
        bundle['artifact_sha256']=file_sha(run/'models/bundle.joblib')
        write_json(run/'model_metadata.json',metadata)
        policies={kind:policy_config(p,kind,tuned['point'],tuned['fixed']) for kind in ('none','fixed','point','gate')}
        write_json(run/'policies.json',policies)
        inference=InferenceEngine(bundle);stream_rows=[];cost_rows=[]
        evaluation=train[train.engine_id.isin(p['partitions']['evaluation'])]
        failures=evaluation.groupby('engine_id').cycle.max().to_dict()
        for scenario in p['scenarios']:
            print('Causal evaluation scenario:',scenario['name'],flush=True)
            for engine,g in evaluation.groupby('engine_id'):
                changed=corrupt(g,scenario,sensor_stds,p['seed'])
                observations=changed.to_dict('records');state={}
                for row in observations:
                    evidence,state=inference.observe(int(engine),int(row['cycle']),{k:row[k] for k in TELEMETRY_CHANNELS},state)
                    stream_rows.append(dict(scenario=scenario['name'],engine_id=int(engine),cycle=int(row['cycle']),
                        prediction=evidence['prediction'],usable=evidence['usable'],lower=evidence['lower'],upper=evidence['upper'],
                        quality_code=evidence['quality']['quality_code'],features_hash=evidence['features_hash'],
                        anomaly_score=evidence['anomaly_score'],persistence=evidence['persistence'],model_id=bundle['model_id']))
                for kind,policy in policies.items():
                    namespace=scenario['name']+'/'+kind
                    store=WorkOrderStore(run/'workflow.db',namespace)
                    replay=CausalReplay(bundle,store,policy)
                    simulate_episode(replay,int(engine),observations,int(failures[engine]))
                    store.close()
            for kind in policies:
                store=WorkOrderStore(run/'workflow.db',scenario['name']+'/'+kind)
                for row in score_ledger(store,failures,p['costs']):
                    cost_rows.append(dict(scenario=scenario['name'],policy=kind,**row))
                store.close()
        csv(run/'scenario_predictions.csv',pd.DataFrame(stream_rows))
        csv(run/'policy_costs.csv',pd.DataFrame(cost_rows))
    # WAL/SHM are mutable SQLite coordination files, never scientific artifacts.
    # Seal after closing all stores; any busy handle makes this run fail.
    finalize_ledger(run/'workflow.db')
    hashes={f.relative_to(run).as_posix():file_sha(f) for f in sorted(run.rglob('*')) if f.is_file()}
    write_json(run/'manifest.json',dict(schema_version=1,protocol_hash=protocol_hash,data_sha256=file_sha(train_file),
                                      artifact_hashes=hashes,selected_model=selected,model_metadata=metadata,
                                      final_evaluation_used_for_selection=False,official_test_read=False))
    print('Independent scorer:',flush=True)
    subprocess.run([sys.executable,'-B',str(PROJECT/'scripts/07_score_phase_a.py'),'--run-dir',str(run),
                    '--data-dir',str(data_dir),'--output',str(run/'independent_score.json')],check=True)
    return run
