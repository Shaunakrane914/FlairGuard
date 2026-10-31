# FD002 experiment reproduction

Read the [completed results](RESULTS.md) and [claim register](CLAIM_REGISTER.md). The [frozen specification](SPECIFICATION.md) defines the hypotheses, engine roles, primary comparisons and failure conditions. Research success requires executed evidence; added model complexity alone is not success.

From the repository root in PowerShell, using the existing Python3.13.5 environment and `requirements-phase-a.lock.txt` (no new runtime dependency is required):

```powershell
$project = 'FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python -B -m pytest -q -p no:cacheprovider

# Every output directory must be new. This fits, freezes development choices,
# executes the final policies and invokes the independent scorer.
python -B "$project/scripts/09_phase_b.py" --run-dir "$project/artifacts/phase_b/my-fd002-reproduction"

# Recheck the saved evidence in isolated mode with only standard-library imports.
# The output filename must also be new.
python -I -B "$project/scripts/10_score_phase_b.py" --run-dir "$project/artifacts/phase_b/my-fd002-reproduction" --data-dir "$project/data/raw" --output "$project/artifacts/phase_b/my-fd002-independent-recheck.json"

# Optional scientific PNG/SVG export; requires matplotlib (observed3.10.8).
python -B "$project/scripts/11_plot_phase_b.py" --run-dir "$project/artifacts/phase_b/my-fd002-reproduction" --output-dir "$project/artifacts/phase_b/my-fd002-figures"
```

The runner reads training trajectories only. A pre-implementation preservation inventory hashes historical files, including official-test bytes for integrity; those files are not loaded as model inputs or evaluated in Phase B. Existing Phase A code/evidence and historical outputs are preserved. All new evidence is under the already ignored `artifacts/phase_b/`. No commit, push, upload or deployment is implied.

## Evidence map

| Artifact | Meaning |
|---|---|
| `run_plan.json`, `protocol.json`, `source/` | Pre-fit source/config/environment fingerprints and frozen memberships |
| `selection.json`, `oof/` | Predictor-fit engine-disjoint candidate selection; fold preprocessing membership |
| `models/`, `model_metadata.json` | Saved global/regime/age/constant models, normalizers, learned selector, complete replay bundle and reload checks |
| `predictions/`, `labels_evaluator_only.csv`, `endpoint_population.csv` | Full-precision candidate predictions for every engine/cycle, separate truth and visible cutoff censoring |
| `selector_metadata.json`, `selector_thresholds.json` | Independent selector-fit provenance and development-only referral thresholds |
| `policy_tuning.json`, `policies.json`, `power_planning.json` | Tuned baseline/candidate policies and development-only approximate power assessment |
| `interval_calibration.json`, `choices_frozen.json` | Independent endpoint interval and all choices frozen before final policy runs |
| `streams/development_*.csv`, `streams/final_*.csv` | Causal operational prediction/availability/error-score histories; development and final engines remain distinct |
| `ledgers/*.db` | Full proposed/committed/executed records through the Phase A work-order store, backed up from offline research memory and sealed before hashing |
| `policy_costs.csv`, `execution_parity.json` | Executed outcomes/cost decomposition and exact parity with the development scheduler |
| `corruption_exposure.csv`, `causality_checks.json` | Raw-injection onset/duration/censoring and saved-model batch/prefix checks |
| `manifest.json`, `independent_score.json` | Immutable artifact inventory and independent metrics, execution validation, clustered uncertainty, budget curves and sensitivity results |

The independent scorer imports the snapshotted standard-library Phase A ledger validator, never application predictors or ML libraries. It verifies model/selector/development/calibration roles, full populations, OOF selection, threshold reconstruction, executed costs, delays and policy freeze. Its statistical comparisons use80 engine clusters, not thousands of scenario-policy episodes as independent samples.

The final policies run in in-memory research stores and become durable only after snapshot. This improves batch evaluation speed without changing the existing durable serving implementation. Do not use this offline runner as an online service or claim a crash-recovery test for an unpersisted batch.

Learned error is a ranking signal, not certified confidence. Intervals are limited clean-endpoint marginal calibrations. All maintenance/inspection costs are hypothetical; no repaired trajectory or physical inspection knowledge is invented. Fresh-environment installation and cross-platform reproduction require separate verification.

The accepted commands used `fd002-v1-run002`, with isolated repeat scoring saved to `validation-v1/independent-recheck.json`. The additional late-prefix verifier and full-life diagnostic sources are saved under `artifacts/phase_b/validation-v1/`; their outputs supplement rather than replace the frozen primary experiment. Output files/directories now exist and intentionally reject reuse. Choose fresh destinations for every reproduction. V1 constants and role counts are fixed; a changed scientific design requires a new reviewed protocol rather than editing tuning fields after evaluation.
