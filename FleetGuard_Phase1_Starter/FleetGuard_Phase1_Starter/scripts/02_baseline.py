"""Step 2: real FD001 RUL baseline; group-disjoint validation and NASA test."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupShuffleSplit
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fleetguard.data import load_subset, add_train_rul, last_cycle_of_each_engine
from fleetguard.features import add_causal_features
from fleetguard.metrics import regression_metrics

RUL_CAP = 125
SEED = 42


def validation_snapshots(df, count_per_engine=3):
    """Simulated snapshots of held-out full-life engines; not official test data."""
    rng = np.random.default_rng(SEED)
    parts = []
    for _, group in df.groupby("engine_id", sort=True):
        # Validation uses only the past at a selected point; target reflects
        # the actual remaining cycles until the complete training trajectory fails.
        allowed = group[(group.cycle >= 20) & group.true_rul.between(5, RUL_CAP)]
        if allowed.empty:
            allowed = group
        indices = rng.choice(allowed.index.to_numpy(), size=min(count_per_engine, len(allowed)), replace=False)
        parts.append(df.loc[indices])
    import pandas as pd
    return pd.concat(parts, ignore_index=True)


def make_model():
    return HistGradientBoostingRegressor(
        loss="squared_error", learning_rate=0.07, max_iter=180,
        max_leaf_nodes=15, min_samples_leaf=20, l2_regularization=1.0,
        random_state=SEED,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    ap.add_argument("--subset", default="FD001", choices=["FD001", "FD002", "FD003", "FD004"])
    args = ap.parse_args()
    train, test, official_rul = load_subset(args.data_dir, args.subset)
    train, features = add_causal_features(add_train_rul(train))
    test, _ = add_causal_features(test)
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    fit_idx, valid_idx = next(splitter.split(train, groups=train.engine_id))
    fit_set = train.iloc[fit_idx]
    heldout = train.iloc[valid_idx]
    assert set(fit_set.engine_id).isdisjoint(set(heldout.engine_id))
    val_snapshots = validation_snapshots(heldout)
    model = make_model()
    model.fit(fit_set[features], np.clip(fit_set.true_rul, 0, RUL_CAP))
    val_predictions = np.clip(model.predict(val_snapshots[features]), 0, RUL_CAP)
    val_metrics = regression_metrics(val_snapshots.true_rul, val_predictions)
    print("Validation (held-out training engines; synthetic cutoffs, NOT official test):")
    print(json.dumps(val_metrics, indent=2))
    # No hyperparameter tuning using official test. This is a single evaluation
    # of the fixed-baseline model fitted on all training trajectories.
    final_model = make_model()
    final_model.fit(train[features], np.clip(train.true_rul, 0, RUL_CAP))
    last_rows = last_cycle_of_each_engine(test, official_rul)
    predictions = np.clip(final_model.predict(last_rows[features]), 0, RUL_CAP)
    test_metrics = regression_metrics(last_rows.true_rul, predictions)
    print("NASA official test (last observed cycle per engine; do NOT tune on this score):")
    print(json.dumps(test_metrics, indent=2))
    print(f"Features: {len(features)}; engine IDs intentionally excluded")

if __name__ == "__main__":
    main()
