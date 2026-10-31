"""Cross-validation and uncertainty quantification for FlairGuard AI.

Implements single engine-disjoint k-fold cross-validation to describe fold variability (not predictive uncertainty).
"""
from typing import Dict, List, Any
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from flairguard.models import get_model_candidates, SEED, RUL_CAP
from flairguard.metrics import regression_metrics


def run_engine_kfold(
    train_df: pd.DataFrame,
    features: List[str],
    n_splits: int = 5,
    seed: int = SEED,
) -> Dict[str, Dict[str, Any]]:
    """Evaluate candidate models using GroupKFold over engine IDs.
    
    Args:
        train_df: Labeled training DataFrame with true_rul and engineered features.
        features: List of feature column names.
        n_splits: Number of disjoint engine folds (e.g. 5 folds = 20 engines per fold for FD001).
        seed: Random seed for candidate model initialization.
        
    Returns:
        Dictionary mapping model names to cross-validation statistics (mean +/- std).
    """
    gkf = GroupKFold(n_splits=n_splits)
    groups = train_df["engine_id"].to_numpy()
    
    candidate_names = list(get_model_candidates(seed=seed).keys())
    fold_metrics = {name: {"mae": [], "rmse": [], "phm08": []} for name in candidate_names}
    
    for fold, (train_idx, val_idx) in enumerate(gkf.split(train_df, groups=groups), start=1):
        fold_train = train_df.iloc[train_idx]
        fold_val = train_df.iloc[val_idx]
        
        # Verify strict engine disjointness
        assert set(fold_train.engine_id).isdisjoint(set(fold_val.engine_id)), f"Leakage in fold {fold}"
        
        # We sample validation snapshots to simulate real-time monitoring of held-out engines
        rng = np.random.default_rng(seed + fold)
        val_snapshots = []
        for _, group in fold_val.groupby("engine_id", sort=True):
            allowed = group[group.cycle >= 20]
            if allowed.empty:
                allowed = group
            idx = rng.choice(allowed.index.to_numpy(), size=min(3, len(allowed)), replace=False)
            val_snapshots.append(fold_val.loc[idx])
        val_snap_df = pd.concat(val_snapshots, ignore_index=True)
        
        X_train = fold_train[features]
        y_train = np.clip(fold_train.true_rul, 0, RUL_CAP)
        X_val = val_snap_df[features]
        y_val_truth = val_snap_df.true_rul.to_numpy()
        
        for name in candidate_names:
            model = get_model_candidates(seed=seed)[name]
            model.fit(X_train, y_train)
            preds = np.clip(model.predict(X_val), 0, RUL_CAP)
            metrics = regression_metrics(y_val_truth, preds)
            
            fold_metrics[name]["mae"].append(metrics["mae_cycles"])
            fold_metrics[name]["rmse"].append(metrics["rmse_cycles"])
            fold_metrics[name]["phm08"].append(metrics["phm08_score"])
            
    summary = {}
    for name, m_dict in fold_metrics.items():
        summary[name] = {
            "cv_mae_mean": round(float(np.mean(m_dict["mae"])), 4),
            "cv_mae_std": round(float(np.std(m_dict["mae"])), 4),
            "cv_rmse_mean": round(float(np.mean(m_dict["rmse"])), 4),
            "cv_rmse_std": round(float(np.std(m_dict["rmse"])), 4),
            "cv_phm08_mean": round(float(np.mean(m_dict["phm08"])), 4),
            "cv_phm08_std": round(float(np.std(m_dict["phm08"])), 4),
            "raw_folds": m_dict,
        }
    return summary


# Compatibility name only: one GroupKFold run, never repeated CV or interval calibration.
run_repeated_engine_kfold = run_engine_kfold
