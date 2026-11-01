"""Bounded empirical fleet bootstrap that re-executes shared resource interactions."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import joblib,numpy as np,pandas as pd
from flairguard.phase_d.study import execute,write_json,write_csv
from flairguard.evidence import file_sha


def run(source,output,replicates):
    output.mkdir(parents=True,exist_ok=False)
    p=json.loads((source/'protocol.json').read_text())
    policy_choices=json.loads((source/'choices_before_corrupted_evaluation.json').read_text())['FD004']
    risk_thresholds=json.loads((source/'risk_choices_before_evaluation.json').read_text())['thresholds']
    protocol=dict(id='phase-d-resource-aware-bootstrap-pilot-v1',replicates=replicates,seed=2026110105,
        cohort='All 49 previously exposed FD004 evaluation engines',scenarios=['clean','packet_40'],
        conditions=p['conditions'][:2],sampling='Engine trajectories sampled with replacement; duplicates get distinct asset identities',
        queues='All policies re-executed on identical sampled fleets; resource competition recomputed',
        purpose='Bounded descriptive uncertainty pilot, not a replacement for all-scenario primary results',
        model_tuning=False,source_manifest=file_sha(source/'manifest.json'),
        limitations='Empirical source cohort only; finite Monte Carlo budget; no fresh confirmation or promotion')
    write_json(output/'protocol.json',protocol)
    risk=joblib.load(source/'models/FD004_decision_risk.joblib')
    truths=pd.read_csv(source/'evaluator_only/FD004_truth.csv')
    deaths={int(e):int((g.cycle+g.true_rul).iloc[0]) for e,g in truths.groupby('engine_id')}
    ids=sorted(deaths);streams={}
    for scenario in protocol['scenarios']:
        frame=pd.read_csv(source/f'predictions/FD004_{scenario}_bounded_last.csv',float_precision='round_trip')
        for name,values in risk.predict(frame).items():frame['risk_'+name]=values
        streams[scenario]={int(e):g.copy() for e,g in frame.groupby('engine_id')}
    rng=np.random.default_rng(protocol['seed']);draws=[];records=[];started=time.perf_counter()
    for replicate in range(replicates):
        selected=list(map(int,rng.choice(ids,size=len(ids),replace=True)));draws.append(selected)
        for scenario in protocol['scenarios']:
            pieces=[]
            for asset,origin in enumerate(selected,start=1):
                copied=streams[scenario][origin].copy();copied['engine_id']=asset;pieces.append(copied)
            frame=pd.concat(pieces,ignore_index=True)
            world={asset:deaths[origin] for asset,origin in enumerate(selected,start=1)}
            for condition in protocol['conditions']:
                for policy in ['point','risk_logistic','risk_boosted','risk_residual']:
                    choice=dict(policy_choices)
                    if policy!='point':choice['risk_threshold']=risk_thresholds[policy.removeprefix('risk_')]
                    name=f'{replicate}-{scenario}-{condition["name"]}-{policy}'
                    events,rows,gw=execute(frame,world,condition,policy,choice,p['costs'],name)
                    # Retain complete ledgers for sampled fleets, including duplicate-origin assets.
                    write_json(output/'ledgers'/f'{name}.json',dict(context=dict(replicate=replicate,scenario=scenario,
                        condition=condition,policy=policy,origin_engines=selected),world=gw,costs=p['costs'],events=events))
                    records.append(dict(replicate=replicate,scenario=scenario,condition=condition['name'],policy=policy,
                        mean_cost=float(np.mean([r['total_cost'] for r in rows])),failures=sum(r['failures'] for r in rows)))
        if replicate%10==0:print('resampled fleets',replicate+1,'seconds',round(time.perf_counter()-started,1),flush=True)
    frame=pd.DataFrame(records);write_csv(output/'replicate_results.csv',frame);write_json(output/'engine_draws.json',draws)
    average=frame.groupby(['replicate','policy'])[['mean_cost','failures']].mean().unstack('policy')
    results=[]
    for policy in ['risk_logistic','risk_boosted','risk_residual']:
        difference=average['mean_cost'][policy]-average['mean_cost']['point']
        failure_difference=average['failures'][policy]-average['failures']['point']
        results.append(dict(policy=policy,source_engines=49,resampled_fleets=replicates,
            mean_cost_difference=float(difference.mean()),empirical_percentile_range_95=list(map(float,np.quantile(difference,[.025,.975]))),
            mean_failure_difference=float(failure_difference.mean()),
            scope='Resource-aware empirical bootstrap pilot on two scenarios; not fresh confirmation'))
    write_json(output/'summary.json',results)
    write_json(output/'manifest.json',dict(files={str(f.relative_to(output)):file_sha(f) for f in output.rglob('*') if f.is_file()},
        wall_seconds=time.perf_counter()-started,engine_episodes=len(records)*49,independent_cost_reconstruction='PASS'))
    print(json.dumps(dict(policy_runs=len(records),engine_episodes=len(records)*49)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--replicates',type=int,default=100);args=p.parse_args();run(args.run,args.output,args.replicates)
