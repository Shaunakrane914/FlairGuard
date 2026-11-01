"""Independent isolated-process verifier: stdlib only, snapshotted scorer and raw NASA files."""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path


def verify(run,data):
    manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    for relative,sha in manifest['files'].items():
        if hashlib.sha256((run/relative.replace(chr(92),'/')).read_bytes()).hexdigest()!=sha:raise AssertionError('Changed artifact: '+relative)
    p=json.loads((run/'protocol.json').read_text(encoding='utf-8'))
    deaths={}
    for ds,lineage in p['lineage'].items():
        if set(lineage['evaluation'])&set(lineage['predictor_fit']+lineage['preprocessing_fit']):
            raise AssertionError('Evaluation engine trained the predictor/preprocessing')
        path=data/f'train_{ds}.txt'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=p['data_hashes'][ds]:raise AssertionError('NASA source mismatch')
        maxima={}
        for line in path.read_text().splitlines():
            row=line.split();eid=int(row[0]);cycle=int(row[1]);maxima[eid]=max(maxima.get(eid,0),cycle)
        deaths[ds]=maxima
    folds=json.loads((run/'risk_oof_lineage.json').read_text())
    held=[]
    for fold in folds:
        if set(fold['risk_training_engines'])&set(fold['predictor_fit']+fold['preprocessing_fit']):raise AssertionError('OOF leakage')
        held+=fold['risk_training_engines']
    if sorted(held)!=sorted(p['lineage']['FD004']['predictor_fit']):raise AssertionError('OOF population incomplete')
    spec=importlib.util.spec_from_file_location('sealed_phase_d_scorer',run/'source/scorer.py')
    scorer=importlib.util.module_from_spec(spec);spec.loader.exec_module(scorer)
    with (run/'per_engine_outcomes.csv').open(newline='') as stream:
        saved={(r['run_id'],int(r['engine_id'])):r for r in csv.DictReader(stream)}
    checked=episodes=0;seen=set()
    for path in sorted((run/'ledgers').glob('*.json')):
        report=json.loads(path.read_text());context=report['context'];ds=context['subset'];condition=context['condition']
        expected=sorted(p['lineage'][ds]['evaluation'])
        if condition['fleet_limit']:expected=expected[:condition['fleet_limit']]
        world={eid:deaths[ds][eid]+((eid*7)%condition['offset'] if condition['offset'] else 0) for eid in expected}
        if world!={int(e):v for e,v in report['evaluator_failure_ticks'].items()}:raise AssertionError('Failure time or population mismatch')
        independent=scorer.score(report['events'],world,condition,p['costs'])
        production={r['engine_id']:r for r in report['production_outcomes']}
        for row in independent:
            key=(path.stem,row['engine_id']);actual=saved[key];prod=production[row['engine_id']]
            if key in seen:raise AssertionError('Duplicate episode')
            seen.add(key)
            for key2 in ['total_cost','failures','completed','queue_wait','downtime','inspections','wasted_cycles','busy_bay_cycles']:
                if abs(float(actual[key2])-row[key2])>1e-9:raise AssertionError('Independent mismatch: '+str(key)+' '+key2)
            if abs(prod['total_cost']-row['total_cost'])>1e-9 or prod['outcome']!=row['outcome']:
                raise AssertionError('Production accounting mismatch')
        checked+=1;episodes+=len(independent)
    if seen!=set(saved):raise AssertionError('Unscored saved episodes')
    return dict(status='PASS',policy_runs=checked,engine_episodes=episodes,
        independent_engines={ds:len(x['evaluation']) for ds,x in p['lineage'].items()},
        checks=['full artifact integrity','raw-source-derived complete failure timeline','fit/preprocessing/evaluation isolation',
                'OOF risk training isolation','all committed/executed actions','capacity/lead/completion boundaries','independent cost and workload reconstruction'],
        manifest_sha256=hashlib.sha256((run/'manifest.json').read_bytes()).hexdigest())


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=verify(args.run.resolve(),args.data.resolve());args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result))
