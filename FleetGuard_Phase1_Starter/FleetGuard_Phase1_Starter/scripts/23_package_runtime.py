"""Provision verified local data/models/evidence into a clean runtime payload."""
import argparse,json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flairguard.evidence import file_sha


def package(project,output):
    output.mkdir(parents=True,exist_ok=False)
    sources=[]
    # Checksum-bound source files; no replacement or synthetic dataset generation.
    for subset in ['FD001','FD002','FD003','FD004']:
        sources += [project/f'data/raw/{prefix}_{subset}.txt' for prefix in ['train','test','RUL']]
    for folder in ['phase_a/fd001-v1-run002','phase_b/fd002-v1-run002','coverage_study/run001']:
        root=project/'artifacts'/folder
        m=json.loads((root/'manifest.json').read_text())
        hashes=m.get('artifact_hashes',m.get('files'))
        for relative,sha in hashes.items():
            relative=relative.replace(chr(92),'/')
            # Runtime needs bundles, evidence tables/protocols, and OOF tables. Large
            # research streams and ledgers remain in their original research package.
            if relative.startswith(('source/','streams/','ledgers/')) or relative.endswith(('.db','.sqlite')):continue
            source=root/relative
            if file_sha(source)!=sha:raise ValueError('Source integrity failure: '+str(source))
            sources.append(source)
        sources.append(root/'manifest.json')
    latest=project/'artifacts/phase_d/latest.json'
    pointer=json.loads(latest.read_text());root=latest.parent/pointer['run']
    if file_sha(root/'manifest.json')!=pointer['manifest_sha256']:raise ValueError('Phase D manifest changed')
    phase=json.loads((root/'manifest.json').read_text())
    for relative,sha in phase['files'].items():
        source=root/relative.replace(chr(92),'/')
        if file_sha(source)!=sha:raise ValueError('Phase D artifact changed')
        sources.append(source)
    sources += [latest,root/'manifest.json']
    for source in sources:
        target=output/source.relative_to(project);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    inventory={str(f.relative_to(output)):file_sha(f) for f in output.rglob('*') if f.is_file()}
    (output/'payload-manifest.json').write_text(json.dumps(dict(files=inventory,source='Verified local NASA/model artifacts; no new labels'),indent=2))
    print(json.dumps(dict(output=str(output),files=len(inventory))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();package(Path(__file__).resolve().parents[1],args.output)
