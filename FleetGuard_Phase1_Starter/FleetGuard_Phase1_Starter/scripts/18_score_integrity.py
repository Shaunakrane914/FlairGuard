"""Independent stdlib-only verification of sealed scheduler experiment outputs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def score(folder):
    manifest=json.loads((folder/'manifest.json').read_text())
    for relative,expected in manifest['files'].items():
        actual=hashlib.sha256((folder/relative).read_bytes()).hexdigest()
        if actual!=expected:
            raise AssertionError('Manifest mismatch: '+relative)
    source=folder/'source/scheduler_scorer.py'
    spec=importlib.util.spec_from_file_location('sealed_independent_scorer',source)
    scorer=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    protocol=json.loads((folder/'protocol.json').read_text())
    checked=episodes=0
    for ds in protocol['datasets']:
        profiles=json.loads((folder/f'{ds}_operational_inputs.json').read_text())
        for p in profiles:
            if set(p)-{'engine_id','max_cycle','observations','model_id','artifact_sha256'}:
                raise AssertionError('Operational profile contains non-observational fields')
            if not p['artifact_sha256'] or len(p['artifact_sha256'])!=64:
                raise AssertionError('Missing saved model hash')
        world={int(k):v for k,v in json.loads((folder/f'{ds}_evaluator_only.json').read_text()).items()}
        if set(world)!={p['engine_id'] for p in profiles}:
            raise AssertionError('Population mismatch')
        for condition in protocol['conditions']:
            for policy in ['FCFS','EDF','RUL_PRIORITY','RISK_AWARE']:
                path=folder/f"{ds}_{condition['bays']}b_{condition['duration']}d_{policy}_ledger.json"
                report=json.loads(path.read_text())
                independent=scorer.score_events(report['events'],world,condition['bays'],condition['duration'],protocol['costs'])
                for key in ['total_fleet_cost','serviced_count','failure_count']:
                    if abs(independent[key]-report[key])>1e-10:
                        raise AssertionError('Reported action/cost mismatch: '+key)
                for key,value in independent['cost_breakdown'].items():
                    if abs(value-report['cost_breakdown'][key])>1e-10:
                        raise AssertionError('Cost component mismatch: '+key)
                checked+=1
                episodes+=len(world)
    return dict(status='PASS',policy_runs=checked,engine_episodes=episodes,
                checks=['sealed source and artifacts','model provenance on operational profiles',
                        'complete engine population','capacity and completion boundaries','independent execution costs'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    print(json.dumps(score(args.run),indent=2))
