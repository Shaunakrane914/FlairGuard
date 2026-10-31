"""Independent standard-library FD002 metrics, execution and research scoring."""
import argparse
from collections import defaultdict
from contextlib import closing
import csv
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import random
import sqlite3


def read(path):
    with Path(path).open(newline='',encoding='utf8') as f:return list(csv.DictReader(f))


def load(path):return json.loads(Path(path).read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def average(xs):return math.fsum(xs)/len(xs) if xs else None


def quantile(xs,q):
    values=sorted(xs);where=(len(values)-1)*q;low=int(where);high=math.ceil(where)
    return values[low]+(values[high]-values[low])*(where-low)


def interval(xs):return [quantile(xs,.025),quantile(xs,.975)]


def harm_upper(harms,n):
    """Exact one-sided95% binomial upper bound, without scipy."""
    if harms==n:return 1.0
    if harms==0:return 1-.05**(1/n)
    low=0.;high=1.
    for _ in range(80):
        mid=(low+high)/2
        cdf=math.fsum(math.comb(n,k)*mid**k*(1-mid)**(n-k) for k in range(harms+1))
        if cdf>.05:low=mid
        else:high=mid
    return (low+high)/2


def metrics(rows,truth,metric):
    return metric([(float(r['prediction']),truth[int(r['engine_id']),int(r['cycle'])]) for r in rows])


def trust_report(streams,truth,p,thresholds,metric):
    tables=[];strata=[];primary={};primary_rows=[]
    for scenario,rows in streams.items():
        observed=[r for r in rows if int(r['cycle'])==p['endpoint_cycles'][r['engine_id']]]
        finite=[r for r in observed if r['prediction']]
        for selector,key in [('learned_gate','risk_score'),('quality_gate','quality_score')]:
            for budget in p['budgets']:
                threshold=thresholds[selector][str(budget)]
                fixed=[r for r in finite if float(r[key])<=threshold]
                count=len(finite)-math.floor(budget*len(finite))
                ranked=sorted(finite,key=lambda r:(float(r[key]),int(r['engine_id'])))[:count]
                for mode,accepted in [('fixed_threshold',fixed),('batch_rank_diagnostic',ranked)]:
                    losses=[abs(float(r['prediction'])-truth[int(r['engine_id']),int(r['cycle'])]) for r in finite]
                    rng=random.Random(p['seed']);draws=[average(rng.sample(losses,len(accepted))) for _ in range(p['random_rejection_replicates'])] if accepted else []
                    accepted_keys={(r['engine_id'],r['cycle']) for r in accepted}
                    rejected=[r for r in finite if (r['engine_id'],r['cycle']) not in accepted_keys]
                    tables.append(dict(scenario=scenario,selector=selector,budget=budget,mode=mode,n_observed=len(observed),
                        failed_before_cutoff=len(p['partitions']['evaluation'])-len(observed),unavailable_predictions=len(observed)-len(finite),
                        accepted=metrics(accepted,truth,metric),rejected=metrics(rejected,truth,metric),
                        all_finite=metrics(finite,truth,metric),automation_coverage=len(accepted)/len(observed) if observed else None,
                        expected_matched_random_mae=average(losses),random_draw_mean_mae=average(draws),
                        random_draw_95_range=interval(draws) if draws else None,
                        interval_coverage_accepted=average([float(r['lower'])<=truth[int(r['engine_id']),int(r['cycle'])]<=float(r['upper']) for r in accepted])))
                if selector=='learned_gate' and budget==p['primary_budget']:
                    fixed_keys={(r['engine_id'],r['cycle']) for r in fixed}
                    for label,predicate in [(f'regime_{k}',lambda r,k=k:int(r['regime'])==k) for k in range(p['regimes'])]+[
                        ('RUL_0_30',lambda r:truth[int(r['engine_id']),int(r['cycle'])]<=30),
                        ('RUL_31_125',lambda r:30<truth[int(r['engine_id']),int(r['cycle'])]<=125),
                        ('RUL_over125',lambda r:truth[int(r['engine_id']),int(r['cycle'])]>125)]:
                        group=[r for r in observed if predicate(r)];good=[r for r in group if (r['engine_id'],r['cycle']) in fixed_keys]
                        strata.append(dict(scenario=scenario,stratum=label,n=len(group),accepted=metrics(good,truth,metric),automation_coverage=len(good)/len(group) if group else None))
                    if not next(s for s in p['scenarios'] if s['name']==scenario).get('diagnostic_only'):
                        primary[scenario]={int(r['engine_id']):(abs(float(r['prediction'])-truth[int(r['engine_id']),int(r['cycle'])]),(r['engine_id'],r['cycle']) in fixed_keys) for r in finite}
                        primary_rows.extend((r,(r['engine_id'],r['cycle']) in fixed_keys) for r in observed)
    def delta(ids):
        accepted_sum=0.;accepted_n=0;control_sum=0.
        for index in primary.values():
            sample=[index[e] for e in ids if e in index]
            good=[loss for loss,ok in sample if ok]
            if good:
                accepted_sum+=math.fsum(good);accepted_n+=len(good)
                control_sum+=len(good)*average([loss for loss,_ in sample])
        return (accepted_sum-control_sum)/accepted_n if accepted_n else None
    ids=p['partitions']['evaluation'];rng=random.Random(p['seed']+71)
    draws=[delta(rng.choices(ids,k=len(ids))) for _ in range(p['bootstrap_replicates'])];draws=[d for d in draws if d is not None]
    ci=interval(draws) if draws else None
    clean=next(t for t in tables if t['scenario']=='clean' and t['selector']=='learned_gate' and t['budget']==p['primary_budget'] and t['mode']=='fixed_threshold')
    near=[ok for r,ok in primary_rows if truth[int(r['engine_id']),int(r['cycle'])]<=30]
    coverage=average(near)
    passed=bool(ci and ci[1]<0 and clean['automation_coverage']>=1-p['acceptance']['clean_referral_budget'] and coverage is not None and coverage>=p['acceptance']['min_low_rul_coverage'])
    return dict(primary=dict(status='PASS_WITHIN_DECLARED_PROTOCOL' if passed else 'NOT_ESTABLISHED',
                accepted_minus_expected_random_mae=delta(ids),engine_bootstrap_95=ci,
                clean_referral_fraction=1-clean['automation_coverage'] if clean['automation_coverage'] is not None else None,
                low_rul_automation_coverage=coverage,n_independent_engines=len(ids),
                scope='Fixed10% development threshold; nine primary scenarios clustered by engine; interval is not risk ranking'),tables=tables,strata=strata)


def value_report(costs,p,planning):
    primary=[s['name'] for s in p['scenarios'] if not s.get('diagnostic_only')]
    lookup={(r['scenario'],r['policy'],r['engine_id']):r for r in costs};ids=p['partitions']['evaluation']
    paired=[];harms=0
    for e in ids:
        point=average([lookup[s,'point',e]['total_cost'] for s in primary])
        learned=average([lookup[s,'learned_gate',e]['total_cost'] for s in primary])
        paired.append((point,learned));harms+=any(lookup[s,'learned_gate',e]['failures'] and not lookup[s,'point',e]['failures'] for s in primary)
    base=average([a for a,b in paired]);candidate=average([b for a,b in paired]);improvement=1-candidate/base
    rng=random.Random(p['seed']+93);deltas=[];ratios=[]
    for _ in range(p['bootstrap_replicates']):
        sample=rng.choices(paired,k=len(paired));a=average([x for x,y in sample]);b=average([y for x,y in sample]);deltas.append(b-a);ratios.append(1-b/a)
    ci=interval(deltas);upper=harm_upper(harms,len(ids))
    statistical=ci[1]<0 and upper<=p['acceptance']['paired_harm_margin']
    passed=improvement>=p['acceptance']['cost_improvement'] and statistical and planning['power_adequate']
    status='PASS_WITHIN_DECLARED_SIMULATED_PROTOCOL' if passed else ('FAIL_OBSERVED_IMPROVEMENT_TARGET' if improvement<p['acceptance']['cost_improvement'] else 'INCONCLUSIVE')
    aggregates=[]
    for scenario,policy in sorted({(r['scenario'],r['policy']) for r in costs}):
        group=[r for r in costs if r['scenario']==scenario and r['policy']==policy]
        aggregates.append(dict(scenario=scenario,policy=policy,n_engines=len(group),mean_cost=average([r['total_cost'] for r in group]),
            total_cost=math.fsum(r['total_cost'] for r in group),failures=sum(r['failures'] for r in group),
            inspections=sum(r['inspections'] for r in group),mean_wasted_cycles=average([r['wasted_cycles'] for r in group])))
    sensitivity=[]
    for failure,unused,inspection in itertools.product(p['sensitivity']['failure'],p['sensitivity']['unused_cycle'],p['sensitivity']['inspection']):
        means={}
        for kind in ('point','learned_gate','quality_decision','quality_gate','fixed'):
            rows=[lookup[s,kind,e] for s in primary for e in ids]
            means[kind]=average([r['planned']*p['costs']['planned']+r['failures']*failure+r['wasted_cycles']*unused+r['inspections']*inspection for r in rows])
        sensitivity.append(dict(failure_cost=failure,unused_cost=unused,inspection_cost=inspection,mean_cost=means))
    return dict(primary=dict(status=status,point_mean=base,learned_mean=candidate,relative_cost_improvement=improvement,
                paired_cost_difference_95=ci,relative_improvement_95=interval(ratios),paired_harmed_engines=harms,
                paired_harm_one_sided_95_upper=upper,risk_margin=p['acceptance']['paired_harm_margin'],
                development_power_adequate=planning['power_adequate'],n_independent_engines=len(ids)),
                aggregates=aggregates,cost_sensitivity=sensitivity,scope='Hypothetical stopping costs only; changed-lead policies re-executed, fixed-action cost grid rescored')


def score(run,data):
    manifest=load(run/'manifest.json');p=load(run/'protocol.json');choices=load(run/'choices_frozen.json')
    if hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=manifest['protocol_hash']:raise ValueError('Protocol changed')
    for name,expected in manifest['artifact_hashes'].items():
        if name.endswith(('-shm','-wal')) or sha(run/name)!=expected:raise ValueError('Artifact changed: '+name)
    if sha(data/'train_FD002.txt')!=p['data_sha256']:raise ValueError('Raw data changed')
    roles=p['partitions'];all_ids=list(itertools.chain.from_iterable(roles.values()))
    if sorted(all_ids)!=list(range(1,261)) or [len(roles[k]) for k in ('predictor_fit','selector_fit','policy_dev','calibration','evaluation')]!=[100,30,30,20,80]:raise ValueError('Role leakage')
    # Reuse the audited standard-library ledger validator, not application code.
    spec=importlib.util.spec_from_file_location('independent_phase_a',run/'source/scripts/07_score_phase_a.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    truth,lifetimes=audit.raw_truth(data/'train_FD002.txt');selected=manifest['selected_model'];selection=load(run/'selection.json');model_metrics={}
    fit=set(roles['predictor_fit']);expected_fold={e:k for k,ids in enumerate(p['cv_folds']) for e in ids};oof_scores={}
    for fold in selection['folds']:
        if set(fold['fit_engines'])!=fit-set(fold['validation_engines']) or fold['validation_engines']!=p['cv_folds'][fold['fold']]:raise ValueError('Preprocessing/CV leakage')
    for name in p['candidates']:
        oof=read(run/'oof'/f'{name}.csv');keys=[(int(r['engine_id']),int(r['cycle'])) for r in oof]
        if len(keys)!=len(set(keys)) or set(keys)!={k for k in truth if k[0] in fit}:raise ValueError('OOF population')
        if any(int(r['fold'])!=expected_fold[int(r['engine_id'])] for r in oof):raise ValueError('OOF fold mismatch')
        ends=[r for r in oof if int(r['cycle'])==p['endpoint_cycles'][r['engine_id']]]
        m=metrics(ends,truth,audit.metrics);oof_scores[name]=m['rmse']
        if not math.isclose(m['rmse'],selection['selection_metrics'][name]['rmse_cycles'],abs_tol=1e-10):raise ValueError('OOF score mismatch')
        rows=read(run/'predictions'/f'{name}.csv');keys=[(int(r['engine_id']),int(r['cycle'])) for r in rows]
        if len(keys)!=len(set(keys)) or set(keys)!=set(truth):raise ValueError('Candidate prediction population')
        summary={}
        for role,ids in roles.items():
            group=[r for r in rows if r['role']==role]
            if {(int(r['engine_id']),int(r['cycle'])) for r in group}!={k for k in truth if k[0] in ids}:raise ValueError('Candidate role mismatch')
            endpoint=[r for r in group if int(r['cycle'])==p['endpoint_cycles'][r['engine_id']]]
            summary[role]=dict(endpoint=metrics(endpoint,truth,audit.metrics),all_cycles=metrics(group,truth,audit.metrics),
                               unavailable_endpoints=len(ids)-len(endpoint),n_engines=len(ids),fit_is_insample=role=='predictor_fit')
        model_metrics[name]=summary
    if selected!=min(p['candidates'],key=lambda n:oof_scores[n]):raise ValueError('Final metrics selected the model')
    metadata=load(run/'model_metadata.json')
    if any(set(m['fit_engines'])!=fit or m['reload_max_abs']>p['acceptance']['reload_atol'] for m in metadata.values()):raise ValueError('Fit membership/reload')
    selector=load(run/'selector_metadata.json');thresholds=load(run/'selector_thresholds.json');cal=load(run/'interval_calibration.json')
    if set(selector['fit_engines'])!=set(roles['selector_fit']) or set(selector['predictor_engines'])!=fit:raise ValueError('Selector leakage')
    if not set(thresholds['engine_ids'])<=set(roles['policy_dev']) or not set(cal['engines'])<=set(roles['calibration']):raise ValueError('Calibration/development leakage')
    if choices['policies']!=load(run/'policies.json') or choices['selected_model']!=selected:raise ValueError('Choices changed after freeze')
    # Thresholds independently reconstructed from the saved clean development stream.
    dev=read(run/'streams/development_clean.csv');dev=[r for r in dev if int(r['cycle'])==p['endpoint_cycles'][r['engine_id']] and r['available']=='True']
    for selector,key in [('learned_gate','risk_score'),('quality_gate','quality_score')]:
        values=sorted(float(r[key]) for r in dev)
        for budget in p['budgets']:
            if values[math.ceil((len(values)-1)*(1-budget))]!=thresholds['thresholds'][selector][str(budget)]:raise ValueError('Threshold not reproducible')
    tuning=load(run/'policy_tuning.json')
    for kind in ('point','fixed','learned_gate'):
        group=[r for r in tuning if r['policy']['kind']==kind]
        best=min(group,key=lambda r:(r['total_cost'],r['failures'],r['inspections'],r['policy']['threshold'],r['policy']['stale_limit']))
        if best['policy']!=choices['policies'][kind]:raise ValueError('Policy tuning choice mismatch')
    costs=[];streams={};lead_checks=0
    for scenario in p['scenarios']:
        name=scenario['name'];path=run/'ledgers'/f'{name}.db'
        costs.extend(audit.ledger_costs(path,lifetimes,p['costs']))
        stream=read(run/'streams'/f'final_{name}.csv');keys=[(int(r['engine_id']),int(r['cycle'])) for r in stream]
        if len(keys)!=len(set(keys)) or set(keys)!={k for k in truth if k[0] in roles['evaluation']}:raise ValueError('Final stream population')
        if any(r['model_id']!=choices['model_id'] for r in stream):raise ValueError('Mixed model evidence')
        streams[name]=stream
        with closing(sqlite3.connect(path)) as c:
            auth={};review={}
            for cycle,text in c.execute('SELECT cycle,result_json FROM decision_events ORDER BY cycle'):
                result=json.loads(text);order=result.get('committed_order');oid=result.get('work_order_id')
                if order and order['review_required']:review.setdefault(oid,cycle)
                if order and order['action_type'].startswith('WORK_ORDER_') and not order['review_required']:auth.setdefault(oid,cycle)
            contexts={ns:json.loads(text)['policy'] for ns,text in c.execute('SELECT namespace,context_json FROM contexts')}
            for namespace,cycle,kind,oid in c.execute('SELECT namespace,cycle,kind,work_order_id FROM executions'):
                delay=contexts[namespace]['lead_time'] if kind=='MAINTENANCE' else contexts[namespace]['review_delay']
                if cycle-(auth if kind=='MAINTENANCE' else review)[oid]<delay:raise ValueError('Instant/free execution')
                lead_checks+=1
    reported=read(run/'policy_costs.csv');reported={(r['scenario'],r['policy'],int(r['engine_id'])):r for r in reported}
    required={(s['name'],kind,e) for s in p['scenarios'] for kind in choices['policies'] for e in roles['evaluation']}
    for name in p.get('lead_sensitivity_scenarios',['clean','noise_s3','missing']):
        required|={(name,f'{kind}_lead{lead}',e) for kind in ('point','learned_gate') for lead in (1,10) for e in roles['evaluation']}
    actual={(r['scenario'],r['policy'],r['engine_id']) for r in costs}
    if actual!=required or set(reported)!=required or len(costs)!=len(required):raise ValueError('Missing/duplicate final episodes')
    for row in costs:
        saved=reported[row['scenario'],row['policy'],row['engine_id']]
        for key,value in row.items():
            if isinstance(value,(int,float)):
                if not math.isclose(float(saved[key]),value,rel_tol=0,abs_tol=p['acceptance']['cost_atol']):raise ValueError('Executed cost disagreement')
            elif saved[key]!=value:raise ValueError('Outcome mismatch')
    parity=load(run/'execution_parity.json')
    if parity['episodes']!=len(required) or any(r['status']!='PASS' for r in parity['cases']):raise ValueError('Fast/durable parity failure')
    return dict(status='PASS_EVIDENCE_INTEGRITY',selected_model=selected,independent_engines=80,executed_episodes=len(costs),
                independently_checked_executions=lead_checks,model_metrics=model_metrics,
                Trust=trust_report(streams,truth,p,thresholds['thresholds'],audit.metrics),
                Value=value_report(costs,p,load(run/'power_planning.json')),
                limitations=['Public-data internal experiment; no historical blindness claim','No real repair/inspection effectiveness identified',
                             '20 interval calibration engines before cutoff censoring; no regime-conditional guarantee',
                             'Offline in-memory research ledgers durable only after snapshot','Other budgets, strata, transfer and economic cases are diagnostic'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True);parser.add_argument('--data-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=score(args.run_dir,args.data_dir)
    with args.output.open('x',encoding='utf8') as f:json.dump(report,f,indent=2,sort_keys=True,allow_nan=False)
    print('Evidence integrity PASS:',report['executed_episodes'],'episodes;',report['independently_checked_executions'],'executions')
    print('Trust:',report['Trust']['primary']);print('Value:',report['Value']['primary'])
