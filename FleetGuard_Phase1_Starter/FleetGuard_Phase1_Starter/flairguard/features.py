"""Causal feature engineering for FlairGuard AI.

All features are strictly computed using observations at or before the current cycle
for each individual engine to eliminate lookahead bias / data leakage.
"""
from typing import Tuple, List
import pandas as pd

SENSORS = [f"sensor_{i}" for i in range(1, 22)]
RAW_FEATURES = ["cycle"] + [f"setting_{i}" for i in range(1, 4)] + SENSORS


def add_causal_features(df: pd.DataFrame, windows: tuple[int, ...] = (5, 20)) -> Tuple[pd.DataFrame, List[str]]:
    """Compute rolling window summary statistics grouped strictly per engine.
    
    Args:
        df: Input DataFrame containing engine_id, cycle, settings, and sensors.
        windows: Window sizes for rolling historical statistics.
        
    Returns:
        DataFrame with added rolling features, and the list of feature column names.
    """
    df = df.sort_values(["engine_id", "cycle"]).copy()
    features = list(RAW_FEATURES)
    grouped = df.groupby("engine_id", sort=False)
    
    for sensor in SENSORS:
        for window in windows:
            mean_name = f"{sensor}_mean_{window}"
            df[mean_name] = grouped[sensor].transform(
                lambda x: x.rolling(window, min_periods=1).mean()
            )
            features.append(mean_name)
            
    if df[features].isna().any().any():
        raise ValueError("Features unexpectedly contain NaNs")
    return df, features

