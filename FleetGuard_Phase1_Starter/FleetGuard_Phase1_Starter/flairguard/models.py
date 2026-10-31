"""Model definitions and factories for FlairGuard AI benchmarking."""
from typing import Dict, Any
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
import lightgbm as lgb

SEED = 42
RUL_CAP = 125


def get_model_candidates(seed: int = SEED) -> Dict[str, Any]:
    """Returns the candidate models for benchmark comparison under identical conditions."""
    return {
        "Ridge": Pipeline([
            ("scaler", StandardScaler()),
            ("regressor", Ridge(alpha=100.0, random_state=seed))
        ]),
        "Random Forest": RandomForestRegressor(
            n_estimators=100,
            max_depth=15,
            min_samples_leaf=5,
            n_jobs=-1,
            random_state=seed
        ),
        "HistGradientBoosting": HistGradientBoostingRegressor(
            loss="squared_error",
            learning_rate=0.07,
            max_iter=180,
            max_leaf_nodes=15,
            min_samples_leaf=20,
            l2_regularization=1.0,
            random_state=seed
        ),
        "LightGBM": lgb.LGBMRegressor(
            n_estimators=180,
            learning_rate=0.07,
            num_leaves=15,
            min_child_samples=20,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=seed,
            verbose=-1,
            n_jobs=-1
        )
    }

