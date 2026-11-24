"""Regression metrics. MAPE is omitted when a target is too close to zero."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def from_log1p(predicted) -> np.ndarray:
    """Invert a log1p target. Reported metrics and API scores use this scale."""

    return np.clip(np.expm1(np.asarray(predicted, dtype=float)), 0, None)


def regression_metrics(y_true, y_pred) -> dict:
    actual = np.asarray(y_true, dtype=float)
    predicted = np.asarray(y_pred, dtype=float)
    mask = np.abs(actual) > 1e-6
    mape = None
    coverage = 0.0
    if mask.any():
        mape = float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100.0)
        coverage = float(mask.mean())
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)) if len(actual) > 1 else None,
        "mape": mape,
        "mape_defined": mape is not None,
        "mape_coverage": coverage,
    }


def population_stability_index(expected, actual, bins: int = 10) -> float:
    """Distribution shift only. A PSI value is not a performance score."""

    left = np.asarray(expected, dtype=float)
    right = np.asarray(actual, dtype=float)
    edges = np.unique(np.quantile(left, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    expected_counts, _ = np.histogram(left, bins=edges)
    actual_counts, _ = np.histogram(right, bins=edges)
    expected_pct = expected_counts / max(expected_counts.sum(), 1)
    actual_pct = actual_counts / max(actual_counts.sum(), 1)
    expected_pct = np.clip(expected_pct, 1e-6, None)
    actual_pct = np.clip(actual_pct, 1e-6, None)
    return float(np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct)))
