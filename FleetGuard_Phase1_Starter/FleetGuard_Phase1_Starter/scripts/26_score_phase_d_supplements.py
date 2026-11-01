"""Independent stdlib reconstruction of resource-bootstrap, frontier and MATLAB ledgers."""
import argparse,csv,hashlib,json
from pathlib import Path


def verify(source,root,data):
    manifest=json.loads((source/'manifest.json').read_text())
    code=source/'source/scorer.py'
    if hashlib.sha256(code.read_bytes()).hexdigest()!=manifest['files'].get('source\\scorer.py',manifest['files'].get('source/scorer.py')):
        raise AssertionError('Independent scorer source changed')
    namespace={'__name__':'sealed_supplement_scorer'}
    exec(compile(code.read_text(encoding='utf-8'),str(code),'exec'),namespace)
    score=namespace['score'];p=json.loads((source/'protocol.json').read_text())
    def deaths(ds):
        world={}
        for line in (data/f'train_{ds}.txt').read_text().splitlines():
            row=line.split();world[int(row[0])]=int(row[1])
        return world
    original={ds:deaths(ds) for ds in ['FD002','FD003','FD004']}
    checked=episodes=0
    for folder in ['fleet-bootstrap-v1-run001','diagnostics-v1-run001','matlab-similarity-v1-run001']:
        directory=root/folder;m=json.loads((directory/'manifest.json').read_text())
        for name,sha in m['files'].items():
            if hashlib.sha256((directory/name.replace(chr(92),'/')).read_bytes()).hexdigest()!=sha:
                raise AssertionError('Changed supplement: '+name)
        if folder.startswith('fleet'):
            with (directory/'replicate_results.csv').open(newline='') as stream:
                saved={(int(r['replicate']),r['scenario'],r['condition'],r['policy']):r for r in csv.DictReader(stream)}
            for path in (directory/'ledgers').glob('*.json'):
                ledger=json.loads(path.read_text());c=ledger['context'];condition=c['condition']
                world={i:original['FD004'][int(e)] for i,e in enumerate(c['origin_engines'],start=1)}
                if world!={int(k):v for k,v in ledger['world'].items()}:raise AssertionError('Sampled failure map mismatch')
                rows=score(ledger['events'],world,condition,p['costs'])
                result=saved[(c['replicate'],c['scenario'],condition['name'],c['policy'])]
                if abs(sum(r['total_cost'] for r in rows)/len(rows)-float(result['mean_cost']))>1e-9:raise AssertionError('Bootstrap cost mismatch')
                if sum(r['failures'] for r in rows)!=int(result['failures']):raise AssertionError('Bootstrap outcome mismatch')
                checked+=1;episodes+=len(rows)
        elif folder.startswith('diagnostics'):
            with (directory/'conservative_threshold_frontier.csv').open(newline='') as stream:
                saved={(r['subset'],r['scenario'],r['condition'],int(r['threshold'])):r for r in csv.DictReader(stream)}
            for path in (directory/'ledgers').glob('*.json'):
                ds,scenario,condition_name,threshold=path.stem.split('-');threshold=int(threshold.removeprefix('threshold'))
                ledger=json.loads(path.read_text());world={int(k):v for k,v in ledger['world'].items()}
                if any(original[ds][e]!=t for e,t in world.items()):raise AssertionError('Frontier failure map mismatch')
                rows=score(ledger['events'],world,ledger['condition'],p['costs']);result=saved[(ds,scenario,condition_name,threshold)]
                if abs(sum(r['total_cost'] for r in rows)/len(rows)-float(result['mean_cost']))>1e-9:raise AssertionError('Frontier cost mismatch')
                checked+=1;episodes+=len(rows)
        else:
            protocol=json.loads((directory/'protocol.json').read_text())
            if set(protocol['fit'])&set(protocol['evaluation']):raise AssertionError('MATLAB fit/evaluation overlap')
            world={e:original['FD003'][e] for e in protocol['evaluation']}
            with (directory/'per_engine_outcomes.csv').open(newline='') as stream:
                saved={(r['scenario'],r['model'],int(r['engine_id'])):r for r in csv.DictReader(stream)}
            for path in directory.glob('*_ledger.json'):
                scenario,model,_=path.stem.split('_');events=json.loads(path.read_text())
                rows=score(events,world,p['conditions'][0],p['costs'])
                for row in rows:
                    result=saved[(scenario,model,row['engine_id'])]
                    if abs(row['total_cost']-float(result['total_cost']))>1e-9:raise AssertionError('MATLAB policy cost mismatch')
                checked+=1;episodes+=len(rows)
    return dict(status='PASS',policy_runs=checked,engine_episodes=episodes,
        scope='Supplementary empirical resampling, frozen threshold frontier and matched MATLAB comparison; no fresh independent engines')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=verify(args.source,args.root,args.data)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result))
