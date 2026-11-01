"""Bounded Phase D orchestration. All labels stay in training or evaluation code."""
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import sqlite3
import time
import joblib
import numpy as np
import pandas as pd
from flairguard.data import read_trajectories,add_train_rul
from flairguard.evidence import file_sha
from flairguard.regimes import RegimeModel
from flairguard.metrics import regression_metrics
from .protocol import freeze,load_predictor
from .telemetry import prediction_stream,corrupt,fit_reference,MissingAwareModel,decision_features,frame_hash
from .fleet import evaluate_controller
from .risk import DecisionRisk,risk_metrics
from .scorer import score as independent_score


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')


def write_csv(path,frame):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    frame.to_csv(path,index=False,float_format='%.17g')


def production_accounting(events,world,condition,costs):
    """Reporting path, independently checked by scorer.py's state-machine validator."""
    result=[]
    for eid,death in sorted(world.items()):
        own=[e for e in events if e['engine_id']==eid]
        terminal=[e for e in own if e['kind'] in ('COMPLETE','FAILURE')][-1]
        commits=[e for e in own if e['kind']=='COMMIT'];starts=[e for e in own if e['kind']=='START']
        complete=terminal['kind']=='COMPLETE';tick=terminal['tick']
        requested=commits[0]['tick'] if commits else None;started=starts[0]['tick'] if starts else None
        wait=((started if starts else tick)-requested) if commits else 0
        waste=death-tick if complete else 0;downtime=tick-requested if commits else 0
        inspections=sum(e['kind']=='REVIEW_COMPLETE' for e in own)
        value=(0 if complete else costs['failure'])+int(complete)*costs['service']+waste*costs['waste']+wait*costs['delay']+downtime*costs['downtime']+inspections*costs['inspection']
        result.append(dict(engine_id=eid,outcome=terminal['kind'],outcome_tick=tick,total_cost=value))
    return result


def clean_records(stream,bundle):
    stream=stream.copy()
    stream['model_id']=bundle['model_id'];stream['model_sha256']=bundle['artifact_sha256']
    last=stream.prediction.where(stream.available).groupby(stream.engine_id).ffill()
    stream['last_valid_prediction']=last.fillna(125.)
    return stream


def execute(stream,world,condition,policy,choices,costs,namespace,recovery='abstain'):
    threshold=choices['conservative'] if policy=='conservative' else choices['point']
    events,global_world=evaluate_controller(stream,world,condition,policy,threshold,
        choices['fixed'],choices.get('risk_threshold',.5),recovery,namespace)
    production=production_accounting(events,global_world,condition,costs)
    checked=independent_score(events,global_world,condition,costs)
    for a,b in zip(production,checked,strict=True):
        if (a['engine_id'],a['outcome'],a['outcome_tick'])!=(b['engine_id'],b['outcome'],b['outcome_tick']):
            raise AssertionError('Production and independent outcomes disagree')
        if not math.isclose(a['total_cost'],b['total_cost'],rel_tol=0,abs_tol=1e-9):
            raise AssertionError('Production and independent costs disagree')
    return events,checked,global_world


def tune(stream,world,p,costs):
    condition=p['conditions'][0];choices=dict(point=20.,conservative=30.,fixed=140)
    records=[]
    for policy,key,grid in [('point','point',p['tuning']['point_thresholds']),
                            ('conservative','conservative',p['tuning']['conservative_thresholds']),
                            ('fixed','fixed',p['tuning']['fixed_ages'])]:
        trials=[]
        for value in grid:
            candidate=dict(choices);candidate[key]=value
            _,rows,_=execute(stream,world,condition,policy,candidate,costs,'development')
            cost=float(np.mean([r['total_cost'] for r in rows]));trials.append((cost,value))
            records.append(dict(policy=policy,value=value,cost=cost))
        choices[key]=min(trials)[1]
    return choices,records


def run(project,output):
    project,output=Path(project).resolve(),Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    started=time.perf_counter();protocol=freeze(project)
    protocol['data_hashes']={ds:file_sha(project/f'data/raw/train_{ds}.txt') for ds in protocol['lineage']}
    # Durable protocol and code precede all new fits and comparisons.
    write_json(output/'protocol.json',protocol)
    for src in (project/'flairguard/phase_d').glob('*.py'):
        dest=output/'source'/src.name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(src,dest)
    bundles={};raws={};clean={};truths={};choices={};all_outcomes=[];risk_records=[];availability=[];provenance=[]
    checks=[];ledgers=output/'ledgers';ledgers.mkdir();db=sqlite3.connect(output/'ledger.sqlite')
    db.execute('CREATE TABLE events(run_id TEXT, sequence INTEGER, kind TEXT, engine_id INTEGER, tick INTEGER, payload TEXT, PRIMARY KEY(run_id,sequence))')
    db.execute('CREATE TABLE runs(run_id TEXT PRIMARY KEY, context TEXT NOT NULL, world_evaluator_only TEXT NOT NULL)')
    def persist(ds,scenario,recovery,condition,policy,stream,world,choice):
        run_id='-'.join([ds,scenario,recovery,condition['name'],policy])
        context=dict(subset=ds,scenario=scenario,recovery=recovery,condition=condition,policy=policy,
                     choices=choice,input_sha256=frame_hash(stream))
        existing=db.execute('SELECT context FROM runs WHERE run_id=?',(run_id,)).fetchone()
        if existing:
            if json.loads(existing[0])!=context:raise AssertionError('Conflicting duplicate benchmark identity')
            return  # Reuse an exactly identical clean comparator, never count it twice.
        events,rows,gw=execute(stream,world,condition,policy,choice,protocol['costs'],run_id,recovery)
        # Offline benchmark transactions are durable when this complete ledger is sealed.
        with db:
            db.execute('INSERT INTO runs VALUES (?,?,?)',(run_id,json.dumps(context),json.dumps(gw)))
            db.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)',[(run_id,i,e['kind'],e['engine_id'],e['tick'],json.dumps(e,allow_nan=False)) for i,e in enumerate(events)])
        write_json(ledgers/(run_id+'.json'),dict(context=context,events=events,evaluator_failure_ticks=gw,production_outcomes=production_accounting(events,gw,condition,protocol['costs'])))
        for row in rows:all_outcomes.append(dict(run_id=run_id,subset=ds,scenario=scenario,recovery=recovery,condition=condition['name'],policy=policy,**row))
        checks.append(dict(run_id=run_id,engines=len(rows),independent_costs='PASS'))
    # D1: every declared held-out complete life, all fixed comparators.
    for ds in protocol['lineage']:
        print('D1',ds,flush=True)
        bundle,lineage,original=load_predictor(project,ds);bundles[ds]=bundle
        (output/'models').mkdir(exist_ok=True);joblib.dump(bundle,output/'models'/f'{ds}.joblib')
        raw=read_trajectories(project/f'data/raw/train_{ds}.txt');raws[ds]=raw
        roles=lineage;dev=roles['development'] if ds!='FD004' else protocol['risk']['policy_development_engines']
        sample=raw.loc[raw.engine_id.isin(dev)].reset_index(drop=True)
        devstream=clean_records(prediction_stream(bundle,sample),bundle)
        devworld={int(e):int(t) for e,t in sample.groupby('engine_id').cycle.max().items()}
        choice,trials=tune(devstream,devworld,protocol,protocol['costs']);choices[ds]=choice
        write_json(output/'development'/f'{ds}_tuning.json',dict(choices=choice,trials=trials))
        evalraw=raw.loc[raw.engine_id.isin(roles['evaluation'])].reset_index(drop=True)
        clean[ds]=clean_records(prediction_stream(bundle,evalraw),bundle)
        world={int(e):int(t) for e,t in evalraw.groupby('engine_id').cycle.max().items()};truths[ds]=world
        write_csv(output/'predictions'/f'{ds}_clean.csv',clean[ds])
        write_csv(output/'evaluator_only'/f'{ds}_truth.csv',add_train_rul(evalraw)[['engine_id','cycle','true_rul']])
        for eid in roles['evaluation'][:2]:
            trajectory=evalraw.loc[evalraw.engine_id==eid].reset_index(drop=True)
            prefix=prediction_stream(bundle,trajectory.iloc[:80].copy())
            expected=clean[ds].loc[(clean[ds].engine_id==eid)&(clean[ds].cycle<=80)]
            np.testing.assert_allclose(prefix.prediction,expected.prediction,rtol=0,atol=1e-10,equal_nan=True)
        for condition in protocol['conditions']:
            ids=sorted(world)[:condition['fleet_limit']] if condition['fleet_limit'] else sorted(world)
            s=clean[ds].loc[clean[ds].engine_id.isin(ids)]
            for policy in protocol['policies']:
                persist(ds,'clean','abstain',condition,policy,s,{e:world[e] for e in ids},choice)
    write_json(output/'choices_before_corrupted_evaluation.json',choices)
    # D2: FD004 risk fit uses only OOF predictions on original predictor-fit engines.
    ds='FD004';bundle=bundles[ds];raw=raws[ds];lineage=protocol['lineage'][ds]
    fit_ids=lineage['predictor_fit'];oof=[];oof_truth=[];folds=[]
    for fold in range(protocol['risk']['oof_folds']):
        held=fit_ids[fold::3];train_ids=sorted(set(fit_ids)-set(held))
        train=raw.loc[raw.engine_id.isin(train_ids)].reset_index(drop=True)
        part=raw.loc[raw.engine_id.isin(held)].reset_index(drop=True)
        model=RegimeModel('RegimeLightGBM',bundle['models'][bundle['selected']].protocol).fit(train,add_train_rul(train).true_rul)
        if set(model.features_.fit_engines_)&set(held):raise AssertionError('OOF preprocessing leakage')
        joblib.dump(model,output/'models'/f'FD004_oof_{fold}.joblib')
        candidate=dict(models={'RegimeLightGBM':model},selected='RegimeLightGBM',model_id=f'oof-{fold}',min_history=20)
        for case in [protocol['scenarios'][0],protocol['scenarios'][3]]:
            modified,_=corrupt(part,case,protocol['seed'])
            stream=prediction_stream(candidate,modified,'bounded_last')
            stream['scenario']=case['name']
            labels=add_train_rul(part).true_rul.to_numpy();mask=(part.cycle>=20)&(labels>0)
            oof.append(stream.loc[mask].copy());oof_truth.extend(labels[mask])
        folds.append(dict(fold=fold,predictor_fit=train_ids,preprocessing_fit=model.features_.fit_engines_,risk_training_engines=held))
        print('D2 OOF',fold,flush=True)
    oof=pd.concat(oof,ignore_index=True);y=np.asarray(oof_truth)
    write_json(output/'risk_oof_lineage.json',folds);write_csv(output/'risk_oof_predictions.csv',oof)
    write_csv(output/'evaluator_only/risk_oof_truth.csv',pd.DataFrame({'true_rul':y}))
    risk=DecisionRisk().fit(oof,y,15,protocol['seed'])
    calraw=raw.loc[raw.engine_id.isin(protocol['risk']['calibration_engines'])].reset_index(drop=True)
    calparts=[];caltruth=[]
    for case in [protocol['scenarios'][0],protocol['scenarios'][3]]:
        modified,_=corrupt(calraw,case,protocol['seed'])
        stream=prediction_stream(bundle,modified,'bounded_last');labels=add_train_rul(calraw).true_rul.to_numpy()
        stream['scenario']=case['name']
        mask=(calraw.cycle>=20)&(labels>0);calparts.append(stream.loc[mask]);caltruth.extend(labels[mask])
    calstream=pd.concat(calparts,ignore_index=True);risk.calibrate(calstream,np.asarray(caltruth))
    joblib.dump(risk,output/'models/FD004_decision_risk.joblib')
    # Risk thresholds only use policy-development engines and labels, never the exposed evaluation engines.
    devraw=raw.loc[raw.engine_id.isin(protocol['risk']['policy_development_engines'])].reset_index(drop=True)
    devstream=clean_records(prediction_stream(bundle,devraw,'bounded_last'),bundle)
    devscores=risk.predict(devstream);risk_choices={};budgets={}
    devworld={int(e):int(t) for e,t in devraw.groupby('engine_id').cycle.max().items()}
    for name,values in devscores.items():
        devstream['risk_'+name]=values;trials=[]
        for threshold in protocol['risk']['thresholds']:
            choice=dict(choices['FD004'],risk_threshold=threshold)
            _,rows,_=execute(devstream,devworld,protocol['conditions'][0],'risk_'+name,choice,protocol['costs'],'risk-development')
            trials.append((float(np.mean([r['total_cost'] for r in rows])),threshold))
        risk_choices[name]=min(trials)[1]
        budgets[name]={str(b):float(np.nextafter(np.quantile(values,1-b),np.inf)) for b in protocol['risk']['review_budgets']}
    write_json(output/'risk_choices_before_evaluation.json',dict(thresholds=risk_choices,development_budget_thresholds=budgets))
    # D3: six actual recovery mechanisms over the same deterministic raw corruptions.
    for ds in ('FD002','FD004'):
        bundle=bundles[ds];raw=raws[ds];lineage=protocol['lineage'][ds]
        fit=raw.loc[raw.engine_id.isin(lineage['predictor_fit'])].reset_index(drop=True)
        reference=fit_reference(bundle,fit)
        missing=MissingAwareModel(bundle).fit(fit,add_train_rul(fit).true_rul,protocol['seed'])
        joblib.dump(missing,output/'models'/f'{ds}_missing_aware.joblib')
        dev_ids=lineage['development'] if ds=='FD002' else protocol['risk']['policy_development_engines']
        devraw=raw.loc[raw.engine_id.isin(dev_ids)].reset_index(drop=True)
        devclean=prediction_stream(bundle,devraw)
        devworld={int(e):int(t) for e,t in devraw.groupby('engine_id').cycle.max().items()}
        stale_trials=[]
        for limit in protocol['tuning']['stale_limits']:
            values=[]
            for case in [protocol['scenarios'][3],protocol['scenarios'][5]]:
                modified,_=corrupt(devraw,case,protocol['seed'],devclean)
                candidate=clean_records(prediction_stream(bundle,modified,'bounded_last',stale_limit=limit),bundle)
                _,rows,_=execute(candidate,devworld,protocol['conditions'][0],'point',choices[ds],protocol['costs'],'stale-development')
                values.extend(r['total_cost'] for r in rows)
            stale_trials.append((float(np.mean(values)),limit))
        stale_limit=min(stale_trials)[1]
        write_json(output/'development'/f'{ds}_stale_limit.json',dict(selected=stale_limit,trials=stale_trials))
        evalraw=raw.loc[raw.engine_id.isin(lineage['evaluation'])].reset_index(drop=True)
        truth=add_train_rul(evalraw).true_rul.to_numpy()
        ref=bundle['models'][bundle['selected']].features_
        for case in protocol['scenarios']:
            print('D3',ds,case['name'],flush=True)
            modified,records=corrupt(evalraw,case,protocol['seed'],clean[ds],ref);provenance.extend(dict(subset=ds,**r) for r in records)
            for recovery in protocol['recovery']:
                # Risk models were calibrated under the fixed 20-cycle recovery contract.
                # D3's independently tuned bounded-last policy is separately recorded.
                limit=stale_limit if recovery in ('bounded_last','decision_fallback') else 20
                stream=clean_records(prediction_stream(bundle,modified,recovery,reference,missing,stale_limit=limit),bundle)
                write_csv(output/'predictions'/f'{ds}_{case["name"]}_{recovery}.csv',stream)
                eligible=(evalraw.cycle>=20)&(truth>0);available=eligible&stream.available
                m=regression_metrics(truth[available],stream.loc[available,'prediction']) if available.any() else {}
                availability.append(dict(subset=ds,scenario=case['name'],recovery=recovery,
                    engines=len(truths[ds]),alive_rows=int(eligible.sum()),available_rows=int(available.sum()),
                    availability=float(available.sum()/eligible.sum()),**m))
                if ds=='FD004' and recovery=='bounded_last':
                    scores=risk.predict(stream)
                    for name,values in scores.items():
                        stream['risk_'+name]=values
                        for budget in protocol['risk']['review_budgets']:
                            threshold=budgets[name][str(budget)]
                            risk_records.append(dict(scenario=case['name'],model=name,development_budget=budget,
                                threshold=threshold,**risk_metrics(stream.loc[eligible],truth[eligible],values[eligible],threshold)))
                    # Simple decision-specific risk indicators, measured rather than called probabilities.
                    x=decision_features(stream)
                    for name,values in [('conservative',(stream.prediction.fillna(125)<=30).astype(float).to_numpy()),
                        ('slope',((x.slope_5<-.5)&(x.prediction<=40)).astype(float).to_numpy()),
                        ('staleness',(stream.stale_age>=5).astype(float).to_numpy())]:
                        risk_records.append(dict(scenario=case['name'],model=name,development_budget=None,
                            threshold=.5,**risk_metrics(stream.loc[eligible],truth[eligible],values[eligible],.5)))
                    for condition in protocol['conditions'][:2]:
                        for name in scores:
                            persist(ds,case['name'],recovery,condition,'risk_'+name,stream,truths[ds],
                                dict(choices[ds],risk_threshold=risk_choices[name]))
                        persist(ds,case['name'],recovery,condition,'point',stream,truths[ds],choices[ds])
                else:
                    for condition in protocol['conditions'][:2]:
                        persist(ds,case['name'],recovery,condition,'point',stream,truths[ds],choices[ds])
    db.close()
    outcomes=pd.DataFrame(all_outcomes);write_csv(output/'per_engine_outcomes.csv',outcomes)
    write_csv(output/'availability.csv',pd.DataFrame(availability));write_json(output/'risk_metrics.json',risk_records)
    write_json(output/'corruption_manifest.json',provenance);write_json(output/'independent_checks.json',checks)
    # D4 sensitivities re-score FIXED ledgers; capacities/durations/offsets were actually re-executed above.
    summaries=[]
    for keys,g in outcomes.groupby(['subset','scenario','recovery','condition','policy'],sort=False):
        summaries.append(dict(zip(['subset','scenario','recovery','condition','policy'],keys),
            engines=len(g),cost=float(g.total_cost.mean()),failures=int(g.failures.sum()),completed=int(g.completed.sum()),
            inspections=int(g.inspections.sum()),review_requests=int(g.review_requests.sum()),
            mean_wait=float(g.queue_wait.mean()),wasted=float(g.wasted_cycles.mean()),downtime=float(g.downtime.mean())))
    write_json(output/'summary.json',summaries)
    sensitivity=[]
    for failure in protocol['sensitivities']['failure']:
        for waste in protocol['sensitivities']['waste']:
            changed=outcomes.total_cost + (failure-protocol['costs']['failure'])*outcomes.failures+(waste-protocol['costs']['waste'])*outcomes.wasted_cycles
            for (ds,policy),values in outcomes.assign(rescored_cost=changed).groupby(['subset','policy']):
                sensitivity.append(dict(subset=ds,policy=policy,failure_cost=failure,waste_cost=waste,
                    mean_cost=float(values.rescored_cost.mean()),scope='Fixed-action rescore, not policy reoptimization'))
    write_csv(output/'fixed_action_sensitivity.csv',pd.DataFrame(sensitivity))
    paired=[];rng=np.random.default_rng(protocol['seed'])
    d=outcomes.loc[(outcomes.subset=='FD004')&(outcomes.recovery=='bounded_last')]
    for policy in ['risk_logistic','risk_boosted','risk_residual']:
        candidate=d.loc[d.policy==policy];baseline=d.loc[d.policy=='point']
        joined=candidate.merge(baseline,on=['engine_id','scenario','condition'],suffixes=('_candidate','_point'),validate='one_to_one')
        per_engine=(joined.total_cost_candidate-joined.total_cost_point).groupby(joined.engine_id).mean().to_numpy()
        draws=np.mean(per_engine[rng.integers(0,len(per_engine),size=(1000,len(per_engine)))],axis=1)
        harm=int(joined.loc[joined.failures_candidate>joined.failures_point,'engine_id'].nunique())
        mean_point=float(joined.total_cost_point.mean());difference=float(per_engine.mean())
        paired.append(dict(policy=policy,independent_engines=len(per_engine),mean_cost_difference=difference,
            interval_95=list(map(float,np.quantile(draws,[.025,.975]))),incrementally_harmed_engines=harm,
            observed_relative_improvement=-difference/mean_point,
            earned_development_advantage=bool(difference<-.05*mean_point and np.quantile(draws,.975)<0 and harm==0),
            confirmation='No; exposed retrospective cohort; no serving promotion'))
    write_json(output/'paired_engine_results.json',paired)
    # Detailed FD004 diagnostic uses all original evaluation lives, never a favorable endpoint subset.
    raw=raws['FD004'];evalraw=raw.loc[raw.engine_id.isin(truths['FD004'])].reset_index(drop=True)
    labels=add_train_rul(evalraw);stream=clean['FD004'];diag=[]
    for eid,g in stream.assign(true_rul=labels.true_rul.to_numpy()).groupby('engine_id'):
        danger=(g.true_rul<=30)&(g.prediction-g.true_rul>20)&(g.cycle>=20)
        if danger.any():
            indices=g.index[danger];runs=[];run=0;previous=None
            for cyc in g.loc[danger,'cycle']:
                run=run+1 if previous is not None and cyc==previous+1 else 1;runs.append(run);previous=cyc
            diag.append(dict(engine_id=int(eid),dangerous_rows=int(danger.sum()),
                first_cycle=int(g.loc[danger,'cycle'].iloc[0]),first_true_rul=int(g.loc[danger,'true_rul'].iloc[0]),
                last_true_rul=int(g.loc[danger,'true_rul'].iloc[-1]),maximum_consecutive_cycles=max(runs),
                regimes=sorted(map(int,g.loc[danger,'regime'].unique()))))
    write_json(output/'fd004_danger_diagnostic.json',dict(population_engines=49,dangerous_engines=len(diag),engines=diag,
        limitation='Previously exposed diagnostic population, not new confirmation'))
    write_json(output/'execution.json',dict(status='PASS',policy_runs=len(checks),engine_episodes=len(outcomes),
        wall_seconds=time.perf_counter()-started,champions_changed=False))
    files={str(f.relative_to(output)):file_sha(f) for f in output.rglob('*') if f.is_file()}
    write_json(output/'manifest.json',dict(protocol='protocol.json',files=files,scope=protocol['scope']))
    print(json.dumps(dict(output=str(output),policy_runs=len(checks),engine_episodes=len(outcomes))),flush=True)
    return output
