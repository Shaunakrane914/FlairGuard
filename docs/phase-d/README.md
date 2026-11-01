# Phase D reproduction

Read [RESULTS.md](RESULTS.md), [SPECIFICATION.md](SPECIFICATION.md), [API_CONTRACT.md](API_CONTRACT.md) and [acceptance.json](acceptance.json). The source changes are on `fix/scientific-operational-integrity`; no push or merge is authorized/performed. All output commands refuse existing experiment directories. Use a fresh versioned name each time.

Run PowerShell from the repository root. The accepted NASA files and historical bundles must already be provisioned from the verified local research artifacts. This repository does not manufacture labels or download unverified replacement weights. Final saved evidence is under the project `artifacts/phase_d` directory; large evidence is intentionally ignored by Git.

```powershell
$project = Join-Path $PWD 'FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter'
python -m venv .venv-phase-d
& ./.venv-phase-d/Scripts/python.exe -m pip install -r requirements.txt -c requirements-serving.lock.txt
npm --prefix frontend ci
Push-Location frontend
npx playwright install chromium
Pop-Location
npm --prefix frontend run build
```

Activate that environment for the commands below (`& ./.venv-phase-d/Scripts/Activate.ps1`). Numerical constraints match the saved bundle environment; full installed dependency inventories for the actual local and container runs are in `verification-v1` and `docker-release-v3`. The official [Playwright installation guide](https://playwright.dev/docs/intro) describes browser installation. MATLAB is optional and requires its installed toolbox/license; the runtime does not.

```powershell
Push-Location $project
python -m pytest tests -q --junitxml=artifacts/phase_d/repro-tests-v1.xml
python scripts/19_phase_d.py --output artifacts/phase_d/reliability-repro-v1
python -I -B scripts/21_score_phase_d.py --run artifacts/phase_d/reliability-repro-v1 --data data/raw --output artifacts/phase_d/repro-independent-v1.json
python scripts/22_phase_d_diagnostics.py --run artifacts/phase_d/reliability-repro-v1 --output artifacts/phase_d/diagnostics-repro-v1
python scripts/25_fleet_resampling.py --run artifacts/phase_d/reliability-repro-v1 --output artifacts/phase_d/fleet-bootstrap-repro-v1 --replicates 100
python scripts/24_plot_phase_d.py --run artifacts/phase_d/reliability-repro-v1 --output artifacts/phase_d/figures-repro-v1
# Optional actual MATLAB comparison; adjust only the executable location:
python scripts/20_matlab_similarity.py --matlab 'C:/Program Files/MATLAB/R2026b/bin/matlab.exe' --output artifacts/phase_d/matlab-repro-v1
Pop-Location
```

The primary source run took about 430 seconds; timings depend on machine. Repeated stochastic fits can differ across dependency/OS versions; the archived predictions and independent scorer are the canonical executed evidence. The primary saved manifest SHA256 is `1ea3f872ea6f0477fd4991c8a02d2f31732a94c624cac699f65fc0bf52078b32`.

Recheck the **original sealed evidence** without fitting models:

```powershell
Push-Location $project
python -I -B scripts/21_score_phase_d.py --run artifacts/phase_d/reliability-v1-run002 --data data/raw --output artifacts/phase_d/recheck-primary-v2.json
python -I -B scripts/26_score_phase_d_supplements.py --source artifacts/phase_d/reliability-v1-run002 --root artifacts/phase_d --data data/raw --output artifacts/phase_d/recheck-supplements-v2.json
python scripts/27_seal_phase_d.py --output artifacts/phase_d/release-recheck-v2
Pop-Location
```

The supplemental checker verifies the named sealed pilot/frontier/MATLAB directories and every recorded file hash, derives original failure clocks and independently reconstructs their costs. The final seal additionally verifies software/browser/runtime reports and preservation hashes; use a fresh output directory with script 27. It does not rerun the experiments.

```powershell
$env:PHASE_D_BROWSER_OUTPUT = Join-Path $project 'artifacts/phase_d/browser-repro-v1'
npm --prefix frontend run test:e2e
```

Playwright starts/stops its own real API serving the built frontend, uses an isolated database and random operator key, restarts the backend itself and retains screenshots, trace, logs and real API status evidence. It requires the local verified dataset/model artifacts, the completed frontend build and free localhost port 8031. It does not mock model/retraining responses. Run `npx playwright show-trace <trace.zip>` from `frontend` to inspect a saved trace.

```powershell
Push-Location $project
python scripts/23_package_runtime.py --output artifacts/phase_d/runtime-payload-repro-v1
python scripts/17_verify_runtime.py --port 8045 --payload artifacts/phase_d/runtime-payload-repro-v1 --output artifacts/phase_d/process-repro-v1
Pop-Location
docker build -t flairguard-phase-d:repro-v1 .
Push-Location $project
python scripts/17_verify_runtime.py --image flairguard-phase-d:repro-v1 --port 8046 --payload artifacts/phase_d/runtime-payload-repro-v1 --output artifacts/phase_d/docker-repro-v1
Pop-Location
```

The payload command verifies original manifests and copies real NASA data, accepted bundles and evidence. Runtime tests mount it read-only and initialize clean isolated storage. The local `latest.json` points to the sealed primary run; a new exploratory experiment is not silently published to the operator API. Test activation/rollback affects only that test's fresh storage and is explicitly distinct from scientific promotion. Docker test containers are stopped and retained for review; do not prune unrelated user containers or volumes.

For a normal local operator session, set `FLAIRGUARD_API_KEY` to a private value, provision paths using `FLAIRGUARD_DATA_DIR` and `FLAIRGUARD_ARTIFACTS_DIR` as needed, and start `uvicorn flairguard.service.app:app` from the project. Build frontend static assets first. Keep local authenticated use distinct from public deployment. The evidence API reads hash-bound saved results; it never runs experiments or promotes a model on GET.

GitHub Actions source is in `.github/workflows/ci.yml`. It runs data-free causality/math regressions and the frontend build. Full research and browser tests require the separately verified payload; a public CI checkout does not pretend those assets exist. Remote workflow execution and public cloud deployment were not performed.
