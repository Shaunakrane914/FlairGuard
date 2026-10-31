"""Independent stdlib-only scorer. Does not import FlairGuard, sklearn or models.

Reconstructs truth from raw FD001 and costs from committed execution records.
Can be invoked from a clean Python interpreter without ML dependencies.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import sqlite3
from contextlib import closing


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def read_csv(path):
    with Path(path).open(newline='',encoding='utf-8') as stream:return list(csv.DictReader(stream))


def metrics(pairs):
    if not pairs:return dict(n=0,mae=None,rmse=None,nasa_sum=None,nasa_mean=None)
    errors=[pred-true for pred,true in pairs]
    if not all(math.isfinite(e) for e in errors):raise ValueError('Nonfinite score input')
    score=math.fsum(math.expm1(-e/13 if e<0 else e/10) for e in errors)
    return dict(n=len(errors),mae=math.fsum(abs(e) for e in errors)/len(errors),
                rmse=math.sqrt(math.fsum(e*e for e in errors)/len(errors)),
                nasa_sum=score,nasa_mean=score/len(errors))


def raw_truth(path):
    cycles={};last={}
    with Path(path).open() as stream:
        for line in stream:
            cols=line.split()
            if len(cols)!=26:raise ValueError('Wrong raw schema')
            engine,cycle=int(cols[0]),int(cols[1])
            if (engine,cycle) in cycles:raise ValueError('Duplicate source key')
            cycles[engine,cycle]=None;last[engine]=max(last.get(engine,0),cycle)
    return {(e,t):last[e]-t for e,t in cycles},last


def ledger_costs(db_path, failure_cycles, costs):
    """Validate commitments/executions, reconstruct each episode independently."""
    results=[]
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        c.row_factory=sqlite3.Row
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity failed')
        if c.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Broken foreign key')
        if c.execute("SELECT 1 FROM work_orders WHERE status IN ('OPEN','ACKNOWLEDGED','IN_PROGRESS') GROUP BY namespace,asset_id HAVING count(*)>1").fetchone():
            raise ValueError('Multiple active orders')
        for ev in c.execute('SELECT telemetry_json FROM decision_events'):
            raw=json.loads(ev[0])
            if any(k in raw for k in ('true_rul','failure_cycle','max_cycle','T')):raise ValueError('Label entered inference payload')
        for outcome in c.execute('SELECT * FROM episode_outcomes ORDER BY namespace,engine_id'):
            ns,asset,engine=outcome['namespace'],outcome['asset_id'],outcome['engine_id']
            T=failure_cycles[engine]
            events=c.execute('''SELECT x.*,o.cycle AS order_cycle,o.status,o.action_type,o.review_required,
                       e.cycle AS commit_cycle,e.proposal_json
                       FROM executions x JOIN work_orders o USING(work_order_id)
                       JOIN decision_events e ON e.event_id=x.event_id
                       WHERE x.namespace=? AND x.asset_id=?''',(ns,asset)).fetchall()
            maintenance=[e for e in events if e['kind']=='MAINTENANCE']
            inspection=[e for e in events if e['kind']=='INSPECTION']
            if len(maintenance)>1 or len(inspection)>1:raise ValueError('Repeated execution')
            for event in events:
                if not event['commit_cycle'] <= event['cycle'] < T:raise ValueError('Uncommitted/late execution')
            success=outcome['kind']=='MAINTENANCE'
            if success != bool(maintenance):raise ValueError('Proposed maintenance counted as executed')
            if success:
                m=maintenance[0]
                if outcome['cycle']!=m['cycle'] or m['status']!='CLOSED' or m['review_required']:
                    raise ValueError('Executed service has incompatible order state')
                if m['action_type'] not in ('WORK_ORDER_SCHEDULE_MAINTENANCE','WORK_ORDER_IMMEDIATE_OVERHAUL'):
                    raise ValueError('Review-only order executed as maintenance')
            elif outcome['cycle']!=T:
                raise ValueError('Failure outcome not at true failure boundary')
            waste=T-outcome['cycle'] if success else 0
            planned=costs['planned'] if success else 0.0
            failure=0.0 if success else costs['failure']
            unused=waste*costs['unused_cycle'];inspection_cost=len(inspection)*costs['inspection']
            scenario,policy=ns.split('/')
            results.append(dict(scenario=scenario,policy=policy,engine_id=engine,outcome=outcome['kind'],
                  outcome_cycle=outcome['cycle'],planned=int(success),failures=int(not success),
                  inspections=len(inspection),wasted_cycles=waste,planned_cost=planned,failure_cost=failure,
                  unused_cost=unused,inspection_cost=inspection_cost,total_cost=planned+failure+unused+inspection_cost))
    return results


def score_run(run, data_dir):
    run=Path(run);manifest=json.loads((run/'manifest.json').read_text())
    p=json.loads((run/'protocol.json').read_text())
    canonical=json.dumps(p,sort_keys=True,separators=(',',':'),allow_nan=False)
    if hashlib.sha256(canonical.encode()).hexdigest()!=manifest['protocol_hash']:raise ValueError('Protocol digest mismatch')
    if sha(Path(data_dir)/'train_FD001.txt')!=p['data_sha256']:raise ValueError('Raw dataset digest mismatch')
    for name,expected in manifest['artifact_hashes'].items():
        if sha(run/name)!=expected:raise ValueError('Artifact changed: '+name)
    sets=[set(p['partitions'][r]) for r in ('fit','calibration','evaluation')]
    if any(sets[i]&sets[j] for i in range(3) for j in range(i)) or set.union(*sets)!=set(range(1,101)):
        raise ValueError('Engine partition leakage')
    selection=json.loads((run/'selection.json').read_text())
    for fold in selection['folds']:
        if set(fold['fit_engines'])&set(fold['validation_engines']):raise ValueError('OOF leakage')
        if not set(fold['fit_engines']+fold['validation_engines'])<=sets[0]:raise ValueError('Calibration/evaluation used in selection')
    truth,lifetimes=raw_truth(Path(data_dir)/'train_FD001.txt')
    summary={}
    for path in sorted((run/'predictions').glob('*.csv')):
        rows=read_csv(path);keys=[(int(r['engine_id']),int(r['cycle'])) for r in rows]
        if len(set(keys))!=len(keys) or set(keys)!=set(truth):raise ValueError('Missing/duplicate prediction keys')
        for role,ids in p['partitions'].items():
            expected={k for k in truth if k[0] in ids}
            received={(int(r['engine_id']),int(r['cycle'])) for r in rows if r['role']==role}
            if received!=expected:raise ValueError('Prediction role mismatch')
        if manifest['model_metadata'][path.stem]['fit_engines']!=p['partitions']['fit']:raise ValueError('Model fit membership mismatch')
        per_role={}
        for role in p['partitions']:
            group=[r for r in rows if r['role']==role]
            available=[r for r in group if int(r['cycle'])==p['endpoint_cycles'][r['engine_id']]]
            per_engine={e:metrics([(float(r['prediction']),truth[e,int(r['cycle'])]) for r in group if int(r['engine_id'])==e])
                        for e in p['partitions'][role]}
            per_role[role]=dict(endpoint=metrics([(float(r['prediction']),truth[int(r['engine_id']),int(r['cycle'])]) for r in available]),
                                unavailable_endpoints=len(p['partitions'][role])-len(available),
                                all_cycles=metrics([(float(r['prediction']),truth[int(r['engine_id']),int(r['cycle'])]) for r in group]),
                                engine_macro_rmse=math.fsum(m['rmse'] for m in per_engine.values())/len(per_engine),
                                per_engine=per_engine,fit_is_insample=role=='fit')
        summary[path.stem]=per_role
    # Check selection from full-precision saved OOF endpoint predictions, independently.
    selection_scores={}
    for path in sorted((run/'oof').glob('*.csv')):
        rows=read_csv(path)
        expected={k for k in truth if k[0] in sets[0]}
        keys=[(int(r['engine_id']),int(r['cycle'])) for r in rows]
        if len(keys)!=len(set(keys)) or set(keys)!=expected:raise ValueError('Invalid OOF population')
        selected=[r for r in rows if int(r['cycle'])==p['endpoint_cycles'][r['engine_id']]]
        value=metrics([(float(r['prediction']),truth[int(r['engine_id']),int(r['cycle'])]) for r in selected])
        selection_scores[path.stem]=value['rmse']
        if not math.isclose(value['rmse'],selection['selection_metrics'][path.stem]['rmse_cycles'],abs_tol=1e-10):
            raise ValueError('Reported selection score not reproducible')
    if selection_scores[manifest['selected_model']]>min(selection_scores.values())+1e-12:raise ValueError('Wrong selected model')
    costs=ledger_costs(run/'workflow.db',lifetimes,p['costs'])
    reported=read_csv(run/'policy_costs.csv')
    index={(r['scenario'],r['policy'],int(r['engine_id'])):r for r in reported}
    if len(index)!=len(reported) or len(costs)!=len(index):raise ValueError('Cost population mismatch')
    for row in costs:
        old=index[(row['scenario'],row['policy'],row['engine_id'])]
        for key,value in row.items():
            if isinstance(value,(int,float)):
                if not math.isclose(float(old[key]),value,rel_tol=0,abs_tol=1e-9):raise ValueError('Cost/outcome mismatch: '+key)
            elif old[key]!=value:raise ValueError('Outcome text mismatch')
    required={(s['name'],kind,e) for s in p['scenarios'] for kind in ('none','fixed','point','gate') for e in sets[2]}
    if set(index)!=required:raise ValueError('Evaluation episodes omitted')
    aggregates=[]
    for scenario,policy in sorted({(r['scenario'],r['policy']) for r in costs}):
        group=[r for r in costs if r['scenario']==scenario and r['policy']==policy]
        aggregates.append(dict(scenario=scenario,policy=policy,n_engines=len(group),
            total_cost=math.fsum(r['total_cost'] for r in group),failures=sum(r['failures'] for r in group),
            inspections=sum(r['inspections'] for r in group),mean_wasted_cycles=math.fsum(r['wasted_cycles'] for r in group)/len(group)))
    streams=read_csv(run/'scenario_predictions.csv');trust=[]
    for scenario in p['scenarios']:
        rows=[r for r in streams if r['scenario']==scenario['name'] and int(r['cycle'])==p['endpoint_cycles'][r['engine_id']]]
        accepted=[r for r in rows if r['usable']=='True']
        finite=[r for r in rows if r['prediction']]
        random_control=random.Random(p['seed']).sample(finite,len(accepted))
        def pairs(rs):return [(float(r['prediction']),truth[int(r['engine_id']),int(r['cycle'])]) for r in rs]
        covered=[r for r in accepted if float(r['lower'])<=truth[int(r['engine_id']),int(r['cycle'])]<=float(r['upper'])]
        trust.append(dict(scenario=scenario['name'],observed_endpoints=len(rows),unavailable_endpoints=len(sets[2])-len(rows),
            automation_coverage=len(accepted)/len(rows) if rows else None,accepted=metrics(pairs(accepted)),
            rejected=metrics(pairs([r for r in finite if r not in accepted])),all_finite=metrics(pairs(finite)),
            random_rejection_matched_coverage=metrics(pairs(random_control)),
            interval_coverage_accepted=len(covered)/len(accepted) if accepted else None,
            interval_guarantee='none on selected/corrupted/sequential populations; descriptive measurement'))
    return dict(status='PASS',checks=['artifact_integrity','partition_membership','prediction_population','OOF_selection','executions_and_costs'],
                selected_model=manifest['selected_model'],model_metrics=summary,policy_aggregates=aggregates,trust_pilot=trust,
                research_claims={'Trust':'PILOT_ONLY; no superiority established',
                                 'Value':'PILOT_ONLY; 20 evaluation engines, no promotion',
                                 'Execution':'ledger invariants passed; regression/restart evidence reported separately'},
                sample_limit='Zero failures among 20 independent engines still gives about 13.9% one-sided 95% upper bound; not safety certification')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=score_run(args.run_dir,args.data_dir)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2,sort_keys=True,allow_nan=False)
    print('Independent evidence checks PASS; selected model:',report['selected_model'])
    for row in report['policy_aggregates']:print(row)


if __name__=='__main__':
    main()
