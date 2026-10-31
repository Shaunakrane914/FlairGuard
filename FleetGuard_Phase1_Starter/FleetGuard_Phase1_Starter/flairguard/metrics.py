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
    
    if len(actual) == 0 or len(actual) != len(predicted):
        raise ValueError("Expected equal non-empty arrays for evaluation")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Metrics require finite predictions and labels")
        
    delta = predicted - actual
    # PHM08 asymmetric penalty:
    # Overly optimistic (delta > 0) is penalized with exp(delta / 10) - 1
    # Early prediction (delta < 0) is penalized with exp(-delta / 13) - 1
    early_penalty = np.exp(np.minimum(-delta / 13.0, 50.0)) - 1.0
    late_penalty = np.exp(np.minimum(delta / 10.0, 50.0)) - 1.0
    phm08_score = np.where(delta < 0, early_penalty, late_penalty).sum()
    
    return {
        "n_snapshots": int(len(actual)),
        "mae_cycles": round(float(mean_absolute_error(actual, predicted)), 4),
        "rmse_cycles": round(float(np.sqrt(mean_squared_error(actual, predicted))), 4),
        "phm08_score": round(float(phm08_score), 4),
    }

