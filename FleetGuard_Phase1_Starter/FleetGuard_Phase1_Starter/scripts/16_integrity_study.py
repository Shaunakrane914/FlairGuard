"""New descriptive experiment; never modifies accepted Phase A/B/coverage runs."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from scipy.stats import beta
from flairguard.evidence import file_sha
from flairguard.fleet_scheduler import build_profiles_from_dataset, FleetMaintenanceScheduler
from flairguard.scheduler_evaluation import load_failure_times,compare_fleet
from flairguard.scheduler_scorer import score_events
from flairguard.service.config import settings
from flairguard.service.models_registry import model_registry
from flairguard.metrics import regression_metrics
from flairguard.service.routes.evidence import verified_file


def run(output,engine_limit):
    output.mkdir(parents=True,exist_ok=False)
    protocol = dict(id='integrity-descriptive-v1',engine_limit=engine_limit,
        datasets=['FD001','FD002'],engines='first IDs in official test; fixed before inference',
        conditions=[dict(bays=1,duration=10),dict(bays=3,duration=4)],
        threshold=25.,costs=dict(failure=10.,service=1.,waste=.05,delay=.1),
        time='global t = individual cycle; all offsets zero; all engines age through queue and service',
        failure_order='failure at t >= T precedes maintenance completion; all unserviced engines eventually fail',
        beyond_telemetry='no invented sensors or model predictions; current point estimate decreases one per elapsed cycle',
        risk='uncalibrated margin heuristic; no per-engine uncertainty available; margin disabled, hence equivalent to RUL priority',
        inference='saved model on observation-only causal features; truth exclusive to evaluator',
        scope='Descriptive correction experiment, historically exposed datasets; no confirmatory scheduler superiority claim')
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2))
    sources = output/'source'
    for name in ['fleet_scheduler.py','scheduler_evaluation.py','scheduler_scorer.py','serving.py','regimes.py','metrics.py']:
        sources.mkdir(exist_ok=True)
        shutil.copyfile(settings.root_dir/'flairguard'/name,sources/name)
    results = []
    for ds in protocol['datasets']:
        profiles = build_profiles_from_dataset(settings.data_dir,ds,engine_limit)
        (output/f'{ds}_operational_inputs.json').write_text(json.dumps([asdict(p) for p in profiles],indent=2))
        predictions = [dict(engine_id=p.engine_id,cycle=c,prediction=pred,
                           uncertainty_margin=unc,model_id=p.model_id,artifact_sha256=p.artifact_sha256)
                       for p in profiles for c,pred,unc in p.observations]
        pd.DataFrame(predictions).to_csv(output/f'{ds}_predictions.csv',index=False,float_format='%.17g')
        world = load_failure_times(settings.data_dir,ds,[p.engine_id for p in profiles])
        (output/f'{ds}_evaluator_only.json').write_text(json.dumps(world,indent=2))
        for condition in protocol['conditions']:
            scheduler = FleetMaintenanceScheduler(num_bays=condition['bays'],service_duration=condition['duration'])
            for metric in compare_fleet(scheduler,profiles,world):
                scored = score_events(metric.events,world,condition['bays'],condition['duration'],protocol['costs'])
                if not np.isclose(scored['total_fleet_cost'],metric.total_fleet_cost,rtol=0,atol=1e-10):
                    raise AssertionError('Independent cost disagreement')
                name=f"{ds}_{condition['bays']}b_{condition['duration']}d_{metric.policy}"
                (output/(name+'_ledger.json')).write_text(json.dumps(metric.model_dump(),indent=2))
                row=metric.model_dump(exclude={'events'})
                results.append(dict(dataset=ds,**row))
    (output/'scheduler_results.json').write_text(json.dumps(results,indent=2))
    # Audit every available evaluation engine and full history for all fixed comparators.
    coverage,engine_rows=[],[]
    for ds in ['FD003','FD004']:
        p=json.loads(verified_file('coverage_study/run001',ds+chr(92)+'protocol.json').read_text())
        for name in ['RegimeLightGBM','GlobalLightGBM','AgeRidge','MatlabPCAAgeRidge']:
            path=verified_file('coverage_study/run001',ds+chr(92)+name+'_evaluation_predictions.csv')
            frame=pd.read_csv(path)
            for population,group in [('full_life_ge20',frame.loc[frame.cycle>=20]),
                ('frozen_endpoint',frame.loc[frame.cycle==frame.engine_id.map(lambda i:p['endpoint_cycles'][str(i)])])]:
                near=group.loc[group.true_rul<=30]
                danger=near.loc[near.prediction-near.true_rul>20]
                n=near.engine_id.nunique();k=danger.engine_id.nunique()
                coverage.append(dict(dataset=ds,model=name,population=population,
                    expected_engines=len(p['partitions']['evaluation']),available_engines=group.engine_id.nunique(),
                    rows=len(group),near_failure_engines=n,dangerous_engines=k,
                    dangerous_rows=len(danger),near_failure_rows=len(near),
                    one_sided_95_upper_any_danger=float(beta.ppf(.95,k+1,n-k)) if n and k<n else 1. if n else None,
                    source_sha256=file_sha(path),**regression_metrics(group.true_rul,group.prediction)))
            for eid,g in frame.loc[frame.cycle>=20].groupby('engine_id'):
                near=g.loc[g.true_rul<=30]
                engine_rows.append(dict(dataset=ds,model=name,engine_id=int(eid),rows=len(g),
                    near_failure_rows=len(near),dangerous_rows=int(((near.prediction-near.true_rul)>20).sum()),
                    **regression_metrics(g.true_rul,g.prediction)))
    pd.DataFrame(coverage).to_csv(output/'coverage_populations.csv',index=False,float_format='%.17g')
    pd.DataFrame(engine_rows).to_csv(output/'coverage_per_engine.csv',index=False,float_format='%.17g')
    (output/'manifest.json').write_text(json.dumps(dict(python=platform.python_version(),
        files={str(f.relative_to(output)):file_sha(f) for f in output.rglob('*') if f.is_file()},
        inputs={str(settings.data_dir/f'{prefix}_{ds}.txt'):file_sha(settings.data_dir/f'{prefix}_{ds}.txt')
                for ds in protocol['datasets'] for prefix in ['test','RUL']},
        acceptance='Execution integrity only; no calibrated risk or superiority claim'),indent=2))
    print(json.dumps(dict(output=str(output),comparisons=len(results),coverage_populations=len(coverage))))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--engine-limit',type=int,default=300)
    args=parser.parse_args()
    run(args.output,args.engine_limit)
