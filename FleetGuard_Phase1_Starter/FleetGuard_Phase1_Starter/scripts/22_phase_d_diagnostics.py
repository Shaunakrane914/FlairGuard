"""All-engine FD004 warning diagnostics and recovery trade-offs, without any refitting."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from flairguard.phase_d.protocol import load_predictor
from flairguard.phase_d.study import write_csv,write_json,execute
from flairguard.quality import ACTIVE_SENSORS
from flairguard.data import read_trajectories,add_train_rul
from flairguard.evidence import file_sha


def run(folder,output):
    output.mkdir(parents=True,exist_ok=False);project=Path(__file__).resolve().parents[1]
    p=json.loads((folder/'protocol.json').read_text());outcomes=pd.read_csv(folder/'per_engine_outcomes.csv')
    bundle,lineage,_=load_predictor(project,'FD004')
    raw=read_trajectories(project/'data/raw/train_FD004.txt')
    raw=raw.loc[raw.engine_id.isin(lineage['evaluation'])].reset_index(drop=True)
    frame=pd.read_csv(folder/'predictions/FD004_clean.csv');labels=add_train_rul(raw)
    frame['true_rul']=labels.true_rul.to_numpy()
    X,_=bundle['models'][bundle['selected']].features_.transform(raw)
    records=[]
    for eid,g in frame.groupby('engine_id'):
        danger=(g.true_rul<=30)&(g.prediction-g.true_rul>20)&(g.cycle>=20)
        first=int(g.loc[danger,'cycle'].iloc[0]) if danger.any() else None
        past=g.loc[g.cycle<first] if first else g.iloc[:0]
        warning=past.loc[past.prediction<=40]
        sensor_scores=X.loc[g.index[g.cycle.between(max(1,(first or 1)-10),(first or 1)-1)],ACTIVE_SENSORS].abs().mean().sort_values(ascending=False)
        records.append(dict(engine_id=int(eid),dangerous_rows=int(danger.sum()),first_danger_cycle=first,
            first_danger_rul=int(g.loc[danger,'true_rul'].iloc[0]) if first else None,
            previous_forecast_warning_cycle=int(warning.cycle.iloc[0]) if len(warning) else None,
            preceding_channels=sensor_scores.head(3).index.tolist() if first else [],
            preceding_normalized_magnitudes=sensor_scores.head(3).tolist() if first else [],
            interpretation='Fit-reference deviations are descriptive contributors, not physical fault attribution'))
    write_json(output/'fd004_all_engine_diagnostics.json',records)
    # Match each corrupted episode to the same engine's clean policy/recovery/condition.
    clean=outcomes.loc[outcomes.scenario=='clean']
    comparison=outcomes.loc[outcomes.scenario!='clean'].merge(clean,on=['subset','engine_id','policy','recovery','condition'],suffixes=('_corrupt','_clean'),validate='many_to_one')
    comparison['suppressed_order']=comparison.requested_tick_corrupt.isna()&comparison.requested_tick_clean.notna()
    comparison['request_delay']=comparison.requested_tick_corrupt-comparison.requested_tick_clean
    comparison['cost_change']=comparison.total_cost_corrupt-comparison.total_cost_clean
    write_csv(output/'recovery_decision_changes.csv',comparison)
    utilization=[]
    for runid,g in outcomes.groupby('run_id'):
        ledger=json.loads((folder/'ledgers'/f'{runid}.json').read_text());condition=ledger['context']['condition']
        horizon=max(ledger['evaluator_failure_ticks'].values())
        utilization.append(dict(run_id=runid,engine_episodes=len(g),horizon=horizon,
            bay_utilization=g.busy_bay_cycles.sum()/(horizon*condition['bays']),
            technician_utilization=g.busy_bay_cycles.sum()/(horizon*min(condition['bays'],condition['technicians'])),
            failed_queued=int((g.failure_phase=='QUEUED').sum()),failed_in_service=int((g.failure_phase=='IN_SERVICE').sum()),
            failed_unrequested=int((g.failure_phase=='UNREQUESTED').sum())))
    write_csv(output/'utilization_and_failure_phases.csv',pd.DataFrame(utilization))
    # The conservative search selected the same threshold20 as point. Report the
    # whole predeclared threshold grid as sensitivity, without selecting a new winner.
    frontier=[]
    for ds in ['FD002','FD004']:
        truth=pd.read_csv(folder/f'evaluator_only/{ds}_truth.csv')
        world={int(e):int((g.cycle+g.true_rul).iloc[0]) for e,g in truth.groupby('engine_id')}
        for scenario in ['clean','packet_40']:
            stream=pd.read_csv(folder/f'predictions/{ds}_{scenario}_bounded_last.csv')
            for condition in p['conditions'][:2]:
                for threshold in sorted(set(p['tuning']['point_thresholds']+p['tuning']['conservative_thresholds'])):
                    name=f'{ds}-{scenario}-{condition["name"]}-threshold{threshold}'
                    events,rows,gw=execute(stream,world,condition,'point',dict(point=threshold,conservative=threshold,fixed=140),p['costs'],name)
                    write_json(output/'ledgers'/f'{name}.json',dict(events=events,world=gw,condition=condition,costs=p['costs']))
                    frontier.append(dict(subset=ds,scenario=scenario,condition=condition['name'],threshold=threshold,
                        engines=len(rows),failures=sum(r['failures'] for r in rows),
                        mean_cost=float(np.mean([r['total_cost'] for r in rows])),mean_waste=float(np.mean([r['wasted_cycles'] for r in rows]))))
    write_csv(output/'conservative_threshold_frontier.csv',pd.DataFrame(frontier))
    write_json(output/'manifest.json',dict(scope='All-engine retrospective diagnostic; frozen-grid sensitivity; no promotion',
        source_run_manifest=file_sha(folder/'manifest.json'),files={str(f.relative_to(output)):file_sha(f) for f in output.rglob('*') if f.is_file()}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.run,args.output)
