"""Performance evaluation metrics for FlairGuard AI.

Calculates MAE, RMSE, and the official NASA PHM08 asymmetric scoring function.
Overly optimistic RUL predictions (predicting machine has more life than it does)
are penalized exponentially more heavily than early predictions.
"""
from typing import Dict, Sequence
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error


def regression_metrics(y_true: Sequence[float], y_pred: Sequence[float]) -> Dict[str, float]:
    """Calculate MAE, RMSE, and NASA PHM08 asymmetric score.
    
    Args:
        y_true: Ground truth RUL values.
        y_pred: Predicted RUL values.
        
    Returns:
        Dictionary containing snapshot count, MAE, RMSE, and PHM08 score.
    """
    actual = np.asarray(y_true, dtype=float)
    predicted = np.asarray(y_pred, dtype=float)
    
    if actual.ndim != 1 or actual.shape != predicted.shape or not actual.size:
        raise ValueError("Expected equal non-empty one-dimensional arrays")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Metrics require finite predictions and labels")
        
    delta = predicted - actual
    # PHM08 asymmetric penalty:
    # Overly optimistic (delta > 0) is penalized with exp(delta / 10) - 1
    # Early prediction (delta < 0) is penalized with exp(-delta / 13) - 1
    exponent = np.where(delta < 0, -delta / 13.0, delta / 10.0)
    with np.errstate(over="raise"):
        phm08_score = np.expm1(exponent).sum()
    
    return {
        "n_snapshots": int(len(actual)),
        "mae_cycles": float(mean_absolute_error(actual, predicted)),
        "rmse_cycles": float(np.sqrt(mean_squared_error(actual, predicted))),
        "phm08_score": float(phm08_score),
        "phm08_mean": float(phm08_score / len(actual)),
    }

