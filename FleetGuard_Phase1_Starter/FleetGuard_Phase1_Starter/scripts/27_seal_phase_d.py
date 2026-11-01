"""Seal executed Phase D acceptance evidence; never infer success from a launched job.

This checks the existing named release evidence. It does not run an experiment or
grant scientific acceptance. Use a new output directory for every seal.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal(project, output):
    root = project / 'artifacts/phase_d'
    repo = project.parents[1]
    def read(name):
        return json.loads((root / name).read_text(encoding='utf-8'))
    def require(test, reason):
        if not test:
            raise AssertionError(reason)

    require(not output.exists(), 'Refusing to overwrite a prior seal')
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=repo, text=True).strip()
    require(branch == 'fix/scientific-operational-integrity', 'Unexpected branch')
    primary = read('verification-v1/independent_recheck.json')
    supplements = read('verification-v1/supplements.json')
    for item in [primary, supplements]:
        require(item['status'] == 'PASS', 'Independent scoring did not pass')
    require((primary['policy_runs'], primary['engine_episodes']) == (332, 17822), 'Unexpected primary scope')
    require((supplements['policy_runs'], supplements['engine_episodes']) == (1644, 81060), 'Unexpected supplemental scope')
    pointer = read('latest.json')
    require(sha(root / pointer['run'] / 'manifest.json') == primary['manifest_sha256'] == pointer['manifest_sha256'],
            'Research pointer/manifest mismatch')

    historical = read('baseline-v1/historical_hashes.json')
    changed = [name for name, digest in historical.items()
               if not (project / name.replace(chr(92), '/')).is_file()
               or sha(project / name.replace(chr(92), '/')) != digest]
    require(not changed, 'Historical artifact changes: ' + repr(changed))
    require(len(historical) == 760, 'Unexpected preservation population')
    suite = ET.parse(root / 'software-final-v1/tests.xml').getroot().find('testsuite')
    require(suite is not None and int(suite.get('tests')) == 114, 'Missing complete regression report')
    require(all(int(suite.get(k, '0')) == 0 for k in ['failures', 'errors', 'skipped']), 'Regression failure/skip')
    browser = read('browser-release-v3/playwright-report.json')
    workflow = read('browser-release-v3/workflow-evidence.json')
    require(browser['stats']['expected'] == 1 and browser['stats']['unexpected'] == 0
            and browser['stats']['skipped'] == 0 and not browser['errors'], 'Browser did not pass')
    require(workflow['status'] == 'PASS' and workflow['backend_restarted']
            and not workflow['scientific_promotion'] and not workflow['page_errors']
            and not workflow['console_errors']
            and not any(r['status'] >= 500 for r in workflow['api_responses']), 'Browser workflow evidence failed')
    runtimes = [read(folder + '/runtime_report.json') for folder in ['process-release-v3', 'docker-release-v3']]
    for runtime in runtimes:
        require(runtime['status'] == 'PASS' and not runtime['training']['promoted_to_champion'], 'Runtime/governance failed')
        require(runtime['phase_d_run'] == pointer['run'], 'Wrong runtime research provenance')
        require(runtime['original_prediction']['model_id'] == runtime['rollback_prediction']['model_id'], 'Rollback mismatch')
        require(runtime['promoted_prediction']['model_id'] != runtime['original_prediction']['model_id'], 'No real lifecycle activation')
        require(not runtime['availability']['datasets']['FD003']['serving']
                and not runtime['availability']['datasets']['FD004']['serving'], 'Unsupported serving claim')
    require(all(not r['earned_development_advantage'] for r in read('reliability-v1-run002/paired_engine_results.json')),
            'Unexpected scientific disposition')

    evidence = {
        'D1': ('Full-life engine-disjoint predictions verified', 'verification-v1/independent_recheck.json'),
        'D2': ('No evaluator labels in operational decisions', 'software-final-v1/tests.xml'),
        'D3': ('Independent fleet cost reconstruction', 'verification-v1/supplements.json'),
        'D4': ('Trust/risk estimator evaluated against tuned baseline; no general advantage earned', 'reliability-v1-run002/paired_engine_results.json'),
        'D5': ('Six missing-telemetry strategies compared in eight conditions', 'reliability-v1-run002/availability.csv'),
        'D6': ('Costs and safety tradeoffs reported with dependence limits', 'fleet-bootstrap-v1-run001/summary.json'),
        'D7': ('Scheduler capacity and execution invariants pass', 'verification-v1/independent_recheck.json'),
        'D8': ('Actual Chromium end-to-end workflow executed', 'browser-release-v3/workflow-evidence.json'),
        'D9': ('Genuine retraining and blocked scientific promotion preserved', 'process-release-v3/runtime_report.json'),
        'D10': ('Local and Docker restart recovery verified', 'docker-release-v3/runtime_report.json'),
        'D11': ('FD003/FD004 research findings retained; active serving false', 'reliability-v1-run002/fd004_danger_diagnostic.json'),
        'D12': ('All 760 historical artifact hashes unchanged; prior negatives retained', 'baseline-v1/historical_hashes.json'),
    }
    acceptance = dict(
        schema_version=1, phase='D', branch=branch,
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
        checkpoint='326829629bf7957d69c20d2e9ff85e3b513cb89e',
        engineering_status='PASS',
        scope='Retrospective/developmental, hypothetical maintenance; no industrial field confirmation',
        gates={gate: dict(status='PASS', outcome=description, evidence='artifacts/phase_d/' + path)
               for gate, (description, path) in evidence.items()},
        scientific_superiority=dict(status='FAIL', reason='No general risk/lookahead superiority established; retain simpler policy'),
        scientific_promotion=dict(status='BLOCKED', reason='No fresh labeled acceptance cohort'),
        remote_ci=dict(status='NOT RUN'), external_cloud_deployment=dict(status='NOT RUN'),
        industrial_field_validation=dict(status='NOT RUN'),
        regression_tests=114, distinct_primary_engines=169,
        primary_policy_runs=332, primary_engine_episodes=17822,
        supplemental_policy_runs=1644, supplemental_engine_episodes=81060,
        historical_files_verified=len(historical), research_manifest_sha256=primary['manifest_sha256'],
        docker_image_id=runtimes[1]['image_id'],
        limits=[
            'Repeated scenarios/draws are not new independent engines',
            'Fixed-ledger engine ranges are conditional sensitivities, not new-fleet confidence intervals',
            'Resource-aware pilot has 100 empirical draws and two telemetry conditions only',
            'Masked predictor compares complete model/recovery methods, not isolated imputation effects',
            'Benchmark ledger is durable at sealing; live API restart claims come from separate runtime tests',
            'No real repair-response trajectories; clocks age through hypothetical service',
            'FD003/FD004 browsing/research only; scientific champions unchanged',
        ])
    output.mkdir(parents=True)
    (output / 'acceptance.json').write_text(json.dumps(acceptance, indent=2), encoding='utf-8')
    (output / 'preservation.json').write_text(json.dumps(dict(status='PASS', files=len(historical), changed=changed), indent=2), encoding='utf-8')
    # Archive concise evidence with hashes; original large ledgers/predictions stay in place.
    for relative in sorted({v[1] for v in evidence.values()} | {'verification-v1/independent_recheck.json',
                   'browser-release-v3/playwright-report.json', 'process-release-v3/runtime_report.json',
                   'verification-v1/supplements.json'}):
        target = output / 'evidence' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    paths = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=repo, text=True).splitlines()
    sources = {name: sha(repo / name) for name in paths if (repo / name).is_file()
               and not name.startswith('docs/') and (repo / name).suffix in {'.py', '.ts', '.tsx', '.css', '.yml', '.json', '.txt'}}
    (output / 'source_hashes.json').write_text(json.dumps(sources, indent=2), encoding='utf-8')
    index = {str(f.relative_to(root)).replace(chr(92), '/'): sha(f) for f in root.rglob('*')
             if f.is_file() and output.resolve() not in f.resolve().parents and '__pycache__' not in f.parts}
    (output / 'evidence_index.json').write_text(json.dumps(index, indent=2), encoding='utf-8')
    manifest = {str(f.relative_to(output)).replace(chr(92), '/'): sha(f) for f in output.rglob('*') if f.is_file()}
    (output / 'manifest.json').write_text(json.dumps(dict(files=manifest), indent=2), encoding='utf-8')
    print(json.dumps(dict(status='PASS', gates=12, evidence_files=len(index), preserved=len(historical))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    seal(Path(__file__).resolve().parents[1], args.output)
