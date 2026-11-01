"""Allowlisted MATLAB comparison job. No arbitrary user code or model promotion."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from flairguard.evidence import file_sha
from flairguard.metrics import regression_metrics
from flairguard.phase_d.scorer import score


def run(output,matlab):
    source=Path(__file__).with_name('20_matlab_similarity.py')
    spec=importlib.util.spec_from_file_location('allowlisted_comparison',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.run(output,matlab)
    # Supplement the preserved comparison with identical-valid-row error metrics.
    m=pd.read_csv(output/'predictions.csv')
    p=pd.read_csv(output/'python_predictions.csv')
    truth=pd.read_csv(output/'evaluator_only.csv')
    common=m.merge(p[['engine_id','cycle','scenario','prediction']],on=['engine_id','cycle','scenario'],
        suffixes=('_matlab','_python'),validate='one_to_one').merge(truth,on=['engine_id','cycle'],validate='many_to_one')
    common=common.dropna(subset=['prediction_matlab','prediction_python'])
    metrics=[]
    for scenario,rows in common.groupby('scenario'):
        for name in ['matlab','python']:
            metrics.append(dict(scenario=scenario,model=name,scope='Identical common-valid scheduled prefixes',
                **regression_metrics(rows.true_rul,rows['prediction_'+name])))
    (output/'common_valid_metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    protocol=json.loads((output/'protocol.json').read_text())
    project=Path(__file__).resolve().parents[1]
    conditions=json.loads((project/'artifacts/phase_d/reliability-v1-run002/protocol.json').read_text())
    raw=pd.read_csv(project/'data/raw/train_FD003.txt',sep=r'\s+',header=None)
    deaths=raw.groupby(0)[1].max().to_dict();world={e:int(deaths[e]) for e in protocol['evaluation']}
    saved=pd.read_csv(output/'per_engine_outcomes.csv')
    for path in output.glob('*_ledger.json'):
        scenario,model,_=path.stem.split('_')
        rows=score(json.loads(path.read_text()),world,conditions['conditions'][0],conditions['costs'])
        expected=saved[(saved.scenario==scenario)&(saved.model==model)].sort_values('engine_id')
        assert np.allclose([r['total_cost'] for r in sorted(rows,key=lambda r:r['engine_id'])],expected.total_cost,rtol=0,atol=1e-9)
    (output/'independent_score.json').write_text(json.dumps(dict(status='PASS',engine_episodes=80)),encoding='utf-8')
    (output/'scope.json').write_text(json.dumps(dict(schema_version=1,task='fd003_similarity_v1',
        scope='Retrospective research comparison; no active serving or champion promotion',
        source_sha256=file_sha(source),matlab_function_sha256=file_sha(project/'scripts/matlab/phase_d_similarity.m'),
        timing_scope='MATLAB query timings saved; Python comparison latency not instrumented; no speed advantage claim'),indent=2),encoding='utf-8')
    # Seal supplementary evidence together with actual fitted model and predictions.
    (output/'manifest.json').write_text(json.dumps(dict(files={str(f.relative_to(output)).replace(chr(92),'/'):file_sha(f)
        for f in output.rglob('*') if f.is_file() and f.name!='manifest.json'},scope='Application-created MATLAB comparison v1'),indent=2),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--matlab',type=Path,required=True);args=parser.parse_args();run(args.output,args.matlab)
