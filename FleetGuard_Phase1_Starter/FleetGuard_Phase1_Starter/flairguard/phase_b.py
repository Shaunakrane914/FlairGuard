"""Versioned FD002 research runner; final roles cannot tune any component."""
from pathlib import Path
from datetime import datetime, timezone
import copy
import importlib.metadata
import itertools
import math
import platform
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from scipy.stats import norm
from threadpoolctl import threadpool_limits
from .data import read_trajectories, add_train_rul
from .evidence import digest, file_sha, write_json
from .metrics import regression_metrics
from .regimes import RegimeModel, corrupt_measurements, selector_inputs
from .decision_experiments import EvidenceReplay, execute_episode, fast_schedule, schedule_cost
from .storage import WorkOrderStore, finalize_ledger
from .policy_eval import score_ledger
from .quality import TELEMETRY_CHANNELS

PROJECT=Path(__file__).resolve().parents[1]


def csv(path,frame):frame.to_csv(path,index=False,float_format='%.17g',mode='x',lineterminator='\n')


def load_protocol(path,data=None):
    p=__import__('json').loads(Path(path).read_text())
    if p['protocol_id']!='phase-b-fd002-v1' or p['subset']!='FD002':raise ValueError('Unexpected protocol')
    sizes=dict(predictor_fit=100,selector_fit=30,policy_dev=30,calibration=20,evaluation=80)
    all_ids=[]
    for role,n in sizes.items():
        ids=p['partitions'][role]
        if len(ids)!=n or len(set(ids))!=n:raise ValueError('Role count/duplicates')
        all_ids+=ids
    if sorted(all_ids)!=list(range(1,261)):raise ValueError('Engine role leakage')
    if len(p['cv_folds'])!=5 or sorted(itertools.chain.from_iterable(p['cv_folds']))!=sorted(p['partitions']['predictor_fit']):raise ValueError('Invalid fit folds')
    if set(p['endpoint_cycles'])!={str(e) for e in all_ids}:raise ValueError('Missing usage cutoff')
    if data and file_sha(data)!=p['data_sha256']:raise ValueError('Raw FD002 changed')
    return p


def records(frame):
    return frame.astype(object).where(pd.notna(frame),None).to_dict('records')


def predict_stream(raw,models,selected,p,selector=None):
    outputs={name:models[name].predict(raw) for name in set([selected,'GlobalLightGBM','RegimeLightGBM'])}
    values=outputs[selected][0];diag=outputs['RegimeLightGBM'][1]
    stream=raw[['engine_id','cycle']].copy()
    for key in diag:stream[key]=diag[key]
    stream['available']=diag.history_length>=p['min_history']
    stream['raw_prediction']=np.where(stream.available,values,np.nan)
    stream['prediction']=np.where(stream.available,np.clip(values,0,p['rul_cap']),np.nan)
    stream['disagreement']=abs(np.clip(outputs['GlobalLightGBM'][0],0,p['rul_cap'])-np.clip(outputs['RegimeLightGBM'][0],0,p['rul_cap']))
    stream['quality_score']=stream.support_max+stream.flatline.astype(float)*1e6
    stream['risk_score']=np.where(stream.available,np.maximum(0,selector.predict(selector_inputs(stream))) if selector is not None else np.nan,np.nan)
    return stream


def endpoint_mask(frame,p):return np.array([int(t)==p['endpoint_cycles'][str(int(e))] for e,t in zip(frame.engine_id,frame.cycle)])


def policy(p,kind,threshold=20,stale=5,risk_threshold=0,fixed_age=140):
    return dict(kind=kind,threshold=int(threshold),stale_limit=int(stale),risk_threshold=float(risk_threshold),
                fixed_age=int(fixed_age),min_history=p['min_history'],decision_buffer=p['policy']['decision_buffer'],
                lead_time=p['policy']['lead_time'],review_delay=p['policy']['review_delay'],critical_threshold=p['policy']['critical_threshold'])


def prepare_cases(raw,models,selected,p,selector=None,include_diagnostic=False):
    cases={}
    for scenario in p['scenarios']:
        if scenario.get('diagnostic_only') and not include_diagnostic:continue
        changed=corrupt_measurements(raw,scenario,models['RegimeLightGBM'].features_,p['seed'])
        cases[scenario['name']]=(changed,predict_stream(changed,models,selected,p,selector))
    return cases


def grouped_cases(cases):
    return {name:{int(e):records(g) for e,g in stream.groupby('engine_id')} for name,(_,stream) in cases.items()}


def plan_power(deltas,base,n_final,target):
    sd=float(np.std(deltas,ddof=1));effect=float(np.mean(base))*target
    # No observed policy difference is not evidence that an unknown fleet
    # difference has exactly zero variance. Plug-in power would be misleading.
    identifiable=math.isfinite(sd) and sd>1e-12
    se=sd/math.sqrt(n_final) if identifiable else None
    ncp=effect/se if identifiable else None
    power=float(norm.cdf(-1.96-ncp)+1-norm.cdf(1.96-ncp)) if identifiable else None
    return dict(source='policy_dev only; normal-theory approximation, not proof of final power',
                status='APPROXIMATE' if identifiable else 'NOT_ESTIMABLE_ZERO_OBSERVED_PAIRED_VARIANCE',
                n_final=n_final,n_development=len(deltas),paired_sd=sd,reference_mean=float(np.mean(base)),
                five_percent_effect=effect,approximate_power_for_five_percent=power,
                mde_80_percent=2.801585*se if identifiable else None,
                paired_zero_harm_upper=1-.05**(1/n_final),power_adequate=bool(power is not None and power>=.8))


def tune_policies(cases,failures,thresholds,p):
    grouped=grouped_cases(cases);scores=[]
    def score(pol):
        schedules=[(e,fast_schedule(rows,int(failures[e]),pol)) for engines in grouped.values() for e,rows in engines.items()]
        return dict(total_cost=math.fsum(schedule_cost(s,int(failures[e]),p['costs']) for e,s in schedules),
                    failures=sum(s['outcome']=='FAILURE' for _,s in schedules),inspections=sum(len(s['inspection_cycles']) for _,s in schedules))
    def choose(kind,options):
        scored=[dict(policy=pol,**score(pol)) for pol in options];scores.extend(scored)
        return min(scored,key=lambda r:(r['total_cost'],r['failures'],r['inspections'],r['policy']['threshold'],r['policy']['stale_limit']))['policy']
    point=choose('point',[policy(p,'point',t,s) for t in p['policy']['threshold_grid'] for s in p['policy']['stale_grid']])
    fixed=choose('fixed',[policy(p,'fixed',fixed_age=t) for t in p['policy']['fixed_age_grid']])
    risk=thresholds['learned_gate'][str(p['primary_budget'])]
    learned=choose('learned_gate',[policy(p,'learned_gate',point['threshold'],s,risk) for s in p['policy']['stale_grid']])
    quality=thresholds['quality_gate'][str(p['primary_budget'])]
    policies=dict(none=policy(p,'none'),fixed=fixed,point=point,
                  quality_gate=policy(p,'quality_gate',point['threshold'],point['stale_limit'],quality),
                  quality_decision={**learned,'kind':'quality_decision','risk_threshold':quality},learned_gate=learned)
    deltas=[];base=[]
    for e in sorted(failures):
        vals={kind:np.mean([schedule_cost(fast_schedule(engines[e],int(failures[e]),pol),int(failures[e]),p['costs']) for engines in grouped.values()]) for kind,pol in [('point',point),('learned_gate',learned)]}
        base.append(vals['point']);deltas.append(vals['learned_gate']-vals['point'])
    planning=plan_power(deltas,base,len(p['partitions']['evaluation']),p['acceptance']['cost_improvement'])
    return policies,scores,planning


def run_phase_b(protocol_path,data_dir,run_dir):
    run=Path(run_dir);run.mkdir(parents=True,exist_ok=False)
    for name in ('source','models','oof','predictions','streams','ledgers'):(run/name).mkdir()
    path=Path(data_dir)/'train_FD002.txt';p=load_protocol(protocol_path,path);ph=digest(p)
    paths=sorted([*(PROJECT/'flairguard').glob('*.py'),*(PROJECT/'scripts').glob('*.py'),*(PROJECT/'tests').glob('*.py'),
                  PROJECT/'configs/phase_b_fd002_v1.json',PROJECT/'requirements-phase-a.lock.txt'])
    sources={}
    for src in paths:
        rel=src.relative_to(PROJECT);dst=run/'source'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);sources[rel.as_posix()]=file_sha(src)
    shutil.copy2(PROJECT.parents[1]/'docs/phase-b/SPECIFICATION.md',run/'source/SPECIFICATION.md')
    sources['SPECIFICATION.md']=file_sha(run/'source/SPECIFICATION.md')
    env=dict(python=sys.version,platform=platform.platform(),packages={k:importlib.metadata.version(k) for k in ('numpy','pandas','scikit-learn','lightgbm','scipy','joblib','pytest','threadpoolctl')})
    write_json(run/'protocol.json',p);write_json(run/'run_plan.json',dict(protocol_hash=ph,started_utc=datetime.now(timezone.utc).isoformat(),environment=env,source_hashes=sources,official_test_loaded=False))
    raw=read_trajectories(path);truth=add_train_rul(raw)[['engine_id','cycle','true_rul']]
    truth_index=truth.set_index(['engine_id','cycle']).true_rul
    y_for=lambda df:truth_index.loc[list(zip(df.engine_id,df.cycle))].to_numpy()
    csv(run/'labels_evaluator_only.csv',truth)
    roles={e:k for k,ids in p['partitions'].items() for e in ids}
    failures=raw.groupby('engine_id').cycle.max().to_dict()
    csv(run/'endpoint_population.csv',pd.DataFrame([dict(engine_id=e,role=roles[e],cutoff=p['endpoint_cycles'][str(e)],status='AVAILABLE' if p['endpoint_cycles'][str(e)]<=T else 'FAILED_BEFORE_CUTOFF') for e,T in failures.items()]))
    fit=raw[raw.engine_id.isin(p['partitions']['predictor_fit'])];selection={};folds=[]
    with threadpool_limits(limits=p['numerical_threads']):
        for name in p['candidates']:
            parts=[];print('FD002 fit-only CV:',name,flush=True)
            for k,ids in enumerate(p['cv_folds']):
                train=fit[~fit.engine_id.isin(ids)];val=fit[fit.engine_id.isin(ids)]
                model=RegimeModel(name,p).fit(train,y_for(train));values,_=model.predict(val)
                part=val[['engine_id','cycle']].copy();part['raw_prediction']=values;part['prediction']=np.clip(values,0,p['rul_cap']);part['fold']=k;parts.append(part)
                if name==p['candidates'][0]:folds.append(dict(fold=k,fit_engines=model.features_.fit_engines_,validation_engines=ids))
            oof=pd.concat(parts).sort_values(['engine_id','cycle']);csv(run/'oof'/f'{name}.csv',oof)
            endpoint=oof[endpoint_mask(oof,p)];selection[name]=regression_metrics(y_for(endpoint),endpoint.prediction)
        selected=min(p['candidates'],key=lambda n:selection[n]['rmse_cycles'])
        write_json(run/'selection.json',dict(model=selected,selection_metrics=selection,folds=folds,scope='predictor-fit OOF only; all preprocessing refitted within each fold'))
        models={};metadata={};model_id=digest(dict(protocol_hash=ph,source=sources,selected=selected))
        for name in p['candidates']:
            print('FD002 full fit:',name,flush=True)
            model=RegimeModel(name,p).fit(fit,y_for(fit));out=run/'models'/f'{name}.joblib';joblib.dump(model,out)
            loaded=joblib.load(out);a,_=model.predict(raw);b,_=loaded.predict(raw)
            np.testing.assert_allclose(a,b,atol=p['acceptance']['reload_atol'],rtol=0)
            prediction=raw[['engine_id','cycle']].copy();prediction['role']=prediction.engine_id.map(roles);prediction['raw_prediction']=b;prediction['prediction']=np.clip(b,0,p['rul_cap']);csv(run/'predictions'/f'{name}.csv',prediction)
            models[name]=loaded;metadata[name]=dict(sha256=file_sha(out),fit_engines=model.features_.fit_engines_,reload_max_abs=float(np.max(abs(a-b))),
                normalization=model.features_.mode,reference_counts=model.features_.reference_counts_,centers=model.features_.centers_.tolist())
        selector_raw=raw[raw.engine_id.isin(p['partitions']['selector_fit'])]
        print('FD002 independent error-selector fit',flush=True)
        selector_cases=prepare_cases(selector_raw,models,selected,p)
        selector_data=pd.concat([stream.assign(target=np.log1p(abs(stream.prediction-y_for(stream)))) for _,stream in selector_cases.values()])
        usable=selector_data[selector_data.available].copy();weights=1/usable.engine_id.map(usable.groupby('engine_id').size()).to_numpy();weights*=len(weights)/weights.sum()
        cfg=p['selector'];selector=LGBMRegressor(n_estimators=cfg['n_estimators'],num_leaves=cfg['num_leaves'],min_child_samples=cfg['min_child_samples'],learning_rate=.05,random_state=p['seed'],n_jobs=2,verbosity=-1)
        selector.fit(selector_inputs(usable),usable.target,sample_weight=weights)
        joblib.dump(selector,run/'models/error_selector.joblib');loaded=joblib.load(run/'models/error_selector.joblib')
        np.testing.assert_allclose(selector.predict(selector_inputs(usable)),loaded.predict(selector_inputs(usable)),atol=p['acceptance']['reload_atol'],rtol=0);selector=loaded
        write_json(run/'selector_metadata.json',dict(fit_engines=p['partitions']['selector_fit'],predictor_engines=p['partitions']['predictor_fit'],input_features=list(selector_inputs(usable)),target='log1p absolute uncapped-RUL prediction error; not probability',scenarios=list(selector_cases),sha256=file_sha(run/'models/error_selector.joblib')))
        del selector_cases,selector_data,usable
        dev_raw=raw[raw.engine_id.isin(p['partitions']['policy_dev'])];dev_cases=prepare_cases(dev_raw,models,selected,p,selector)
        endpoint=dev_cases['clean'][1];endpoint=endpoint[endpoint_mask(endpoint,p) & endpoint.available]
        if len(endpoint)<10:raise ValueError('Too few independent policy-development endpoints')
        thresholds={kind:{str(b):float(np.quantile(endpoint[key],1-b,method='higher')) for b in p['budgets']} for kind,key in [('learned_gate','risk_score'),('quality_gate','quality_score')]}
        write_json(run/'selector_thresholds.json',dict(thresholds=thresholds,engine_ids=list(map(int,endpoint.engine_id)),scope='clean policy-development usage endpoints only; finite-sample referral targets, no exact test-budget guarantee'))
        dev_fail={e:failures[e] for e in p['partitions']['policy_dev']}
        print('FD002 policy development (independent engines)',flush=True)
        policies,tuning,planning=tune_policies(dev_cases,dev_fail,thresholds,p)
        write_json(run/'policies.json',policies);write_json(run/'policy_tuning.json',tuning);write_json(run/'power_planning.json',planning)
        # Retain development evidence so choices can be independently reconstructed.
        for name,(_,stream) in dev_cases.items():csv(run/'streams'/f'development_{name}.csv',stream)
        cal=raw[raw.engine_id.isin(p['partitions']['calibration'])];pred,_=models[selected].predict(cal);end=endpoint_mask(cal,p)
        residuals=np.abs(y_for(cal)[end]-np.clip(pred[end],0,p['rul_cap']));rank=math.ceil((len(residuals)+1)*(1-p['alpha']))
        if rank>len(residuals):raise ValueError('Insufficient independent interval calibration endpoints')
        q=float(np.sort(residuals)[rank-1]);write_json(run/'interval_calibration.json',dict(q=q,n_engines=len(residuals),rank=rank,alpha=p['alpha'],engines=list(map(int,cal.loc[end,'engine_id'])),scope='single clean usage endpoint; no selective/sequential/regime guarantee'))
        write_json(run/'model_metadata.json',metadata)
        write_json(run/'choices_frozen.json',dict(frozen_utc=datetime.now(timezone.utc).isoformat(),selected_model=selected,model_id=model_id,policies=policies,thresholds=thresholds,interval_q=q,final_evaluation_loaded_into_selection=False))
        joblib.dump(dict(models=models,selected=selected,selector=selector,protocol=p,protocol_hash=ph,
                         policies=policies,thresholds=thresholds,interval_q=q,model_id=model_id),run/'models/bundle.joblib')
        del dev_cases
        evaluation=raw[raw.engine_id.isin(p['partitions']['evaluation'])];cost_rows=[];parity=[];causality=[];exposure=[]
        for scenario in p['scenarios']:
            name=scenario['name'];print('FD002 FINAL scenario:',name,flush=True)
            changed=corrupt_measurements(evaluation,scenario,models['RegimeLightGBM'].features_,p['seed'])
            stream=predict_stream(changed,models,selected,p,selector);stream['model_id']=model_id
            stream['lower']=np.maximum(0,stream.prediction-q);stream['upper']=stream.prediction+q
            csv(run/'streams'/f'final_{name}.csv',stream)
            first=p['partitions']['evaluation'][0];g=changed[changed.engine_id==first]
            for cutoff in (40,140,160,200):
                if cutoff>g.cycle.max():continue
                prefix=predict_stream(g[g.cycle<=cutoff],models,selected,p,selector).iloc[-1]
                batch=stream[(stream.engine_id==first)&(stream.cycle==cutoff)].iloc[0]
                for key in ('prediction','risk_score','quality_score'):
                    if pd.isna(prefix[key]) and pd.isna(batch[key]):continue
                    if not math.isclose(float(prefix[key]),float(batch[key]),abs_tol=p['acceptance']['reload_atol'],rel_tol=0):raise ValueError('Prefix/batch causal mismatch')
                causality.append(dict(scenario=name,engine_id=first,cycle=cutoff,status='PASS'))
            for e,T in ((e,failures[e]) for e in p['partitions']['evaluation']):
                onset=scenario.get('onset');duration=scenario.get('duration',0)
                observed=max(0,min(duration,T-onset+1)) if onset else 0
                exposure.append(dict(scenario=name,engine_id=e,onset=onset,duration=duration,observed_injected_cycles=observed,failure_censored=bool(onset and observed<duration)))
            active_policies=dict(policies)
            if name in p.get('lead_sensitivity_scenarios',['clean','noise_s3','missing']):
                for lead in (1,10):
                    for kind in ('point','learned_gate'):active_policies[f'{kind}_lead{lead}']={**policies[kind],'lead_time':lead}
            # Disposable in-memory research ledger; each namespace's full event
            # history is retained. Backup/sealing is explicit, not online durability.
            store=WorkOrderStore(':memory:')
            for key,pol in active_policies.items():
                store.namespace=name+'/'+key;replay=EvidenceReplay(store,pol,model_id,ph)
                for engine,group in stream.groupby('engine_id'):
                    rows=records(group.drop(columns=['model_id','lower','upper']))
                    telemetry=records(changed.loc[group.index,TELEMETRY_CHANNELS])
                    expected=fast_schedule(rows,int(failures[engine]),pol)
                    actual=execute_episode(replay,int(engine),rows,telemetry,int(failures[engine]))
                    if actual!=expected:raise ValueError('Fast/transactional executed-schedule disagreement')
                    parity.append(dict(scenario=name,policy=key,engine_id=int(engine),status='PASS'))
                cost_rows.extend(dict(scenario=name,policy=key,**r) for r in score_ledger(store,failures,p['costs']))
            with closing(sqlite3.connect(run/'ledgers'/f'{name}.db')) as dest:store.conn.backup(dest)
            store.close();finalize_ledger(run/'ledgers'/f'{name}.db')
        csv(run/'policy_costs.csv',pd.DataFrame(cost_rows));csv(run/'corruption_exposure.csv',pd.DataFrame(exposure))
        write_json(run/'execution_parity.json',dict(status='PASS',episodes=len(parity),cases=parity,durability_scope='offline in-memory execution, then sealed SQLite backup'))
        write_json(run/'causality_checks.json',dict(status='PASS',checks=causality))
    hashes={f.relative_to(run).as_posix():file_sha(f) for f in sorted(run.rglob('*')) if f.is_file()}
    write_json(run/'manifest.json',dict(schema_version=1,protocol_hash=ph,data_sha256=file_sha(path),artifact_hashes=hashes,selected_model=selected,official_test_loaded=False))
    subprocess.run([sys.executable,'-B',str(PROJECT/'scripts/10_score_phase_b.py'),'--run-dir',str(run),'--data-dir',str(data_dir),'--output',str(run/'independent_score.json')],check=True)
    return run
