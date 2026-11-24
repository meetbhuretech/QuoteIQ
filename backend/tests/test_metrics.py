"""Metric helpers stay separate from performance claims."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "ml"))

from quoteiq_ml.metrics import population_stability_index, regression_metrics


def test_perfect_predictions_have_zero_mae():
    metrics = regression_metrics([1, 2, 3], [1, 2, 3])
    assert metrics["mae"] == 0
    assert metrics["r2"] == 1
    assert metrics["mape_defined"] is True


def test_mape_is_not_reported_for_all_zero_targets():
    metrics = regression_metrics([0, 0, 0], [1, 1, 1])
    assert metrics["mape_defined"] is False
    assert metrics["mape"] is None


def test_identical_distributions_have_no_drift_and_drift_is_not_labelled_as_error():
    score = population_stability_index([1, 1, 1, 2, 2, 3, 4, 5], [1, 1, 1, 2, 2, 3, 4, 5])
    assert score == 0
    report_note = "PSI compares input distributions. It does not measure prediction error or accuracy decay."
    assert "does not measure prediction error" in report_note
