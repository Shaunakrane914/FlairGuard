"""Optional, matched FD003 toolbox comparison; independent of application serving."""
import argparse,json,sys,subprocess,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from flairguard.phase_d.protocol import load_predictor
from flairguard.phase_d.study import write_json,write_csv,execute
from flairguard.phase_d.telemetry import prediction_stream,corrupt
from flairguard.data import read_trajectories,add_train_rul
from flairguard.metrics import regression_metrics
from flairguard.evidence import file_sha


def run(output,matlab):
    project=Path(__file__).resolve().parents[1];output.mkdir(parents=True,exist_ok=False)
    bundle,lineage,_=load_predictor(project,'FD003')
    protocol=dict(id='phase-d-matlab-similarity-v1',subset='FD003',fit=lineage['predictor_fit'],
        evaluation=lineage['evaluation'],history='Retrospective diagnostic',
        health_indicator='fit-only early sensor_11 z-score, trailing five-sample mean',
        estimator='Predictive Maintenance Toolbox pairwiseSimilarityModel, correlation, defaults',
        query_grid='every 20 observed cycles >=20; no label-based endpoint selection',
        outages='sensor_11 missing cycles140..159; forward fill at most5; never future fill',
        decision='same sparse forecast grid, bounded last-valid countdown20; point threshold20; no refit or promotion')
    write_json(output/'protocol.json',protocol)
    raw=read_trajectories(project/'data/raw/train_FD003.txt')
    fit=raw.loc[raw.engine_id.isin(lineage['predictor_fit'])].copy()
    early=fit.loc[fit.cycle<=30,'sensor_11'];mean=float(early.mean());sd=max(float(early.std()),1e-3)
    fit['hi']=((fit.sensor_11-mean)/sd).groupby(fit.engine_id).transform(lambda x:x.rolling(5,min_periods=1).mean())
    write_csv(output/'fit.csv',fit[['engine_id','cycle','hi']])
    evaluation=raw.loc[raw.engine_id.isin(lineage['evaluation'])].reset_index(drop=True)
    pieces=[];python=[]
    for scenario in ['clean','missing']:
        changed=evaluation.copy()
        if scenario=='missing':changed.loc[changed.cycle.between(140,159),'sensor_11']=np.nan
        signal=changed.groupby('engine_id').sensor_11.ffill(limit=5)
        hi=((signal-mean)/sd).groupby(changed.engine_id).transform(lambda x:x.rolling(5,min_periods=5).mean())
        q=changed[['engine_id','cycle']].copy();q['hi']=hi;q['scenario']=scenario;pieces.append(q)
        stream=prediction_stream(bundle,changed);stream['scenario']=scenario;python.append(stream)
    write_csv(output/'queries.csv',pd.concat(pieces));write_csv(output/'python_predictions.csv',pd.concat(python))
    write_csv(output/'evaluator_only.csv',add_train_rul(evaluation)[['engine_id','cycle','true_rul']])
    script=str(project/'scripts/matlab').replace(chr(92),'/').replace("'","''")
    folder=str(output.resolve()).replace(chr(92),'/').replace("'","''")
    with (output/'matlab.log').open('x',encoding='utf-8') as log:
        result=subprocess.run([str(matlab),'-batch',f"addpath('{script}'); phase_d_similarity('{folder}')"],stdout=log,stderr=subprocess.STDOUT,timeout=300)
    if result.returncode:raise RuntimeError('MATLAB comparison failed; inspect preserved log')
    predictions=pd.read_csv(output/'predictions.csv')
    gold=add_train_rul(evaluation)[['engine_id','cycle','true_rul']]
    compared=predictions.merge(pd.concat(python)[['engine_id','cycle','scenario','prediction']],on=['engine_id','cycle','scenario'],suffixes=('_matlab','_python'),validate='one_to_one').merge(gold,on=['engine_id','cycle'],validate='many_to_one')
    metrics=[];outcomes=[]
    settings=json.loads((project/'artifacts/phase_d/reliability-v1-run002/protocol.json').read_text())
    world={int(e):int(t) for e,t in evaluation.groupby('engine_id').cycle.max().items()}
    for scenario,g in compared.groupby('scenario'):
        for model in ['matlab','python']:
            available=g['prediction_'+model].notna()
            scored=g.loc[available]
            metrics.append(dict(scenario=scenario,model=model,expected_rows=len(g),available_rows=len(scored),
                expected_engines=len(world),available_engines=int(scored.engine_id.nunique()),
                dangerous_engines=int(scored.loc[(scored.true_rul<=30)&(scored['prediction_'+model]-scored.true_rul>20),'engine_id'].nunique()),
                **regression_metrics(scored.true_rul,scored['prediction_'+model])))
            stream=evaluation[['engine_id','cycle']].merge(g[['engine_id','cycle','prediction_'+model]],on=['engine_id','cycle'],how='left')
            values=[]
            for eid,engine in stream.groupby('engine_id'):
                last=None
                for row in engine.itertuples(index=False,name=None):
                    e,c,pred=row
                    if np.isfinite(pred):last=(c,float(pred))
                    values.append(max(0,last[1]-(c-last[0])) if last and c-last[0]<=20 else np.nan)
            stream['prediction']=values;stream['available']=np.isfinite(values);stream['stale_age']=0
            events,rows,_=execute(stream,world,settings['conditions'][0],'point',dict(point=20.,conservative=30.,fixed=140),settings['costs'],scenario+'-'+model)
            write_json(output/f'{scenario}_{model}_ledger.json',events)
            outcomes.extend(dict(scenario=scenario,model=model,**r) for r in rows)
    write_json(output/'metrics.json',metrics);write_csv(output/'per_engine_outcomes.csv',pd.DataFrame(outcomes))
    write_json(output/'manifest.json',dict(files={str(f.relative_to(output)):file_sha(f) for f in output.rglob('*') if f.is_file()},scope='Optional offline matched diagnostic; no runtime dependency'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--matlab',type=Path,required=True)
    args=p.parse_args();run(args.output,args.matlab)
