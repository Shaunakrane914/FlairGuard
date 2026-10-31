# FleetGuard AI — Phase 1: real-data RUL baseline

Tata Elxsi Teliport S4, Case Study 1 — Self-Healing Machines.

This starter is an **evaluation-first** project. It does not fabricate sensor failures, invent scores, or ship an unrelated dashboard. It starts with verifiable NASA C-MAPSS data and a reproducible first RUL model.

## Get the NASA data

Official dataset page: https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data
Official data archive: https://data.nasa.gov/docs/legacy/CMAPSSData.zip

Extract the downloaded archive and place these files in `data/raw/`:

```
data/raw/train_FD001.txt
data/raw/test_FD001.txt
data/raw/RUL_FD001.txt
```

The extracted archive includes FD002–FD004 for future phases. Don't commit the raw data to a public repository without first checking redistribution terms; preserve NASA attribution.

**Do not confuse** the downloadable *CMAPSS Jet Engine Simulated Data* with a separate NASA page about the C-MAPSS *simulator software*, which has different access restrictions.

## Setup (Windows / PyCharm)

Python 3.11 or 3.12 recommended. In PyCharm Professional, open this folder, create a virtual environment, and use the terminal:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
python scripts/01_inspect.py --data-dir data/raw --subset FD001
python scripts/02_baseline.py --data-dir data/raw --subset FD001
```

If your local Python launcher has no 3.11 installed, create the virtual environment with another supported Python version through PyCharm and install dependencies from `requirements.txt`. If PowerShell blocks activation, use `.venv\Scripts\python.exe` directly instead.

## What the scripts do

- `01_inspect.py`: parses NASA's whitespace-delimited 26-column data, verifies engine IDs, cycle order and RUL alignment, reports missing data and sizes.
- `02_baseline.py`: creates **causal** sensor features using each engine's current/past cycles only, splits training engines into disjoint train/validation groups, fits a gradient-boosted regressor, and prints MAE/RMSE. Then it refits on the complete FD001 training set and evaluates the **official** truncated test trajectories exactly once.
- `tests/`: fast checks using tiny constructed fixture rows **only for software tests**. These are *not* competitive model training data.

## Protocol and limitations

1. Training trajectories run to failure, so for each training row: `RUL = engine_max_cycle - current_cycle`.
2. Training targets are capped at 125 cycles as an explicit modeling choice. Official test ground truth remains **uncapped** for honest scoring.
3. Official test RUL labels apply to the **last available cycle** of each test engine, not every row. We don't construct false labels for intermediate test rows.
4. The engine ID is **not** included as a model feature. The train/validation split is grouped by engine, not a random row split.
5. Validation samples are artificially truncated from held-out *training* engine trajectories to approximate partial observation. Their distribution is not guaranteed to match the official test distribution. It is a development check, not a competition benchmark.
6. Official test metrics are diagnostic **only**, not a source for hyperparameter tuning. Keep further model comparisons on train/validation engines.
7. There are no per-cycle anomaly labels, so we will define and test anomaly criteria separately in Phase 2, without presenting injected anomalies as ground truth.
8. Dataset values are simulated and noisy. C-MAPSS cannot substantiate claims of physical engine-life extension through control interventions.

## Next milestone

Once this script runs and logs real FD001 metrics, implement: (1) simple constant/linear baselines, (2) train/validation experiment tracking, (3) regime-aware normalization for FD002/FD004, (4) justified anomaly detection, (5) risk-aware triage and work-order audit log, and (6) actual MLOps with labeled retraining data.
