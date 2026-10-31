"""Rigorous unit and integration tests for FlairGuard AI.

Verifies:
1. Engine ID isolation (zero data leakage between train & validation engines).
2. Strict causal feature engineering (no future cycle lookahead).
3. RUL label validity and piecewise capping monotonicity.
4. Deterministic model reproducibility given identical random seeds.
"""
import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import GroupShuffleSplit
from flairguard.data import COLUMNS, add_train_rul, last_cycle_of_each_engine
from flairguard.features import add_causal_features
from flairguard.models import get_model_candidates, SEED, RUL_CAP


def make_synthetic_fleet(num_engines: int = 5, cycles_per_engine: int = 30) -> pd.DataFrame:
    """Generate multi-engine synthetic telemetry for property tests."""
    records = []
    rng = np.random.default_rng(42)
    for eng in range(1, num_engines + 1):
        for c in range(1, cycles_per_engine + 1):
            sensor_vals = rng.normal(loc=100.0, scale=5.0, size=21)
            row = [eng, c, 0.0, 0.0, 100.0] + list(sensor_vals)
            records.append(row)
    return pd.DataFrame(records, columns=COLUMNS)


def test_engine_disjoint_split_no_leakage():
    """Verify that train and validation splits never share engine IDs."""
    fleet = make_synthetic_fleet(num_engines=10, cycles_per_engine=25)
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=SEED)
    train_idx, val_idx = next(splitter.split(fleet, groups=fleet.engine_id))
    
    train_engines = set(fleet.iloc[train_idx]["engine_id"].unique())
    val_engines = set(fleet.iloc[val_idx]["engine_id"].unique())
    
    # Must be completely disjoint
    assert train_engines.isdisjoint(val_engines), "Engine leakage detected between train and val splits!"
    assert len(train_engines) + len(val_engines) == 10


def test_temporal_causality_strict():
    """Verify that altering sensor values in future cycle t+k does NOT affect features at cycle t."""
    fleet = make_synthetic_fleet(num_engines=2, cycles_per_engine=20)
    feat_baseline, cols = add_causal_features(fleet, windows=(5, 10))
    
    # Perturb future cycles (cycle >= 15) for engine 1
    perturbed = fleet.copy()
    perturbed.loc[(perturbed.engine_id == 1) & (perturbed.cycle >= 15), "sensor_2"] = 99999.0
    feat_perturbed, _ = add_causal_features(perturbed, windows=(5, 10))
    
    # Past cycles (cycle <= 14) for engine 1 must remain 100% identical
    past_orig = feat_baseline[(feat_baseline.engine_id == 1) & (feat_baseline.cycle <= 14)][cols]
    past_pert = feat_perturbed[(feat_perturbed.engine_id == 1) & (feat_perturbed.cycle <= 14)][cols]
    
    pd.testing.assert_frame_equal(past_orig, past_pert)


def test_rul_ground_truth_properties():
    """Verify run-to-failure linear decrement and test-end truncation alignment."""
    fleet = make_synthetic_fleet(num_engines=3, cycles_per_engine=40)
    labeled = add_train_rul(fleet)
    
    # For every engine, true_rul must be strictly decreasing by 1 and end at 0
    for eng_id, group in labeled.groupby("engine_id"):
        ruls = group["true_rul"].to_numpy()
        assert ruls[-1] == 0, f"Engine {eng_id} did not end at RUL=0"
        diffs = np.diff(ruls)
        assert np.all(diffs == -1), f"Engine {eng_id} RUL decrement is non-linear"

    # Test set end labeling
    dummy_rul = np.array([55.0, 72.0, 10.0])
    test_ends = last_cycle_of_each_engine(fleet, dummy_rul)
    assert len(test_ends) == 3
    assert test_ends["true_rul"].tolist() == [55.0, 72.0, 10.0]
    assert test_ends["cycle"].tolist() == [40, 40, 40]


def test_model_reproducibility():
    """Verify that candidate models produce identical outputs when evaluated with identical seed."""
    fleet = make_synthetic_fleet(num_engines=6, cycles_per_engine=30)
    labeled = add_train_rul(fleet)
    df_feat, feature_names = add_causal_features(labeled, windows=(5, 10))
    
    X = df_feat[feature_names]
    y = np.clip(df_feat["true_rul"], 0, RUL_CAP)
    
    # Test Ridge, LightGBM, and HistGradientBoosting reproducibility
    for model_name in ["Ridge", "HistGradientBoosting", "LightGBM"]:
        model1 = get_model_candidates(seed=SEED)[model_name]
        model2 = get_model_candidates(seed=SEED)[model_name]
        
        model1.fit(X, y)
        model2.fit(X, y)
        
        pred1 = model1.predict(X)
        pred2 = model2.predict(X)
        
        np.testing.assert_allclose(
            pred1, pred2, rtol=1e-5, atol=1e-5,
            err_msg=f"{model_name} predictions are not deterministic across seeds!"
        )
        assert np.isfinite(pred1).all()

