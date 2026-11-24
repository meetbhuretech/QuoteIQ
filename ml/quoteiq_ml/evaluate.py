"""Recompute holdout metrics and a drift report.

Drift here is a comparison of feature distributions. It is not model error.
Performance is computed only from labels in the holdout file.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from quoteiq_ml.metrics import from_log1p, population_stability_index, regression_metrics
from quoteiq_ml.spec import FEATURE_COLUMNS, NUMERIC_FEATURES, TARGETS

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def evaluate() -> dict:
    holdout_path = ARTIFACTS / "holdout.csv"
    train_path = ARTIFACTS / "train_split.csv"
    if not holdout_path.exists() or not train_path.exists():
        raise FileNotFoundError("Train the model before evaluation so holdout.csv exists.")
    holdout = pd.read_csv(holdout_path)
    train = pd.read_csv(train_path)
    metadata = json.loads((ARTIFACTS / "metadata.json").read_text()) if (ARTIFACTS / "metadata.json").exists() else {}
    transform = (metadata.get("parameters") or {}).get("target_transform")
    metrics = {}
    for target in TARGETS:
        model = joblib.load(ARTIFACTS / f"{target}.joblib")
        raw = model.predict(holdout[FEATURE_COLUMNS])
        predicted = from_log1p(raw) if transform == "log1p" else np.asarray(raw, dtype=float)
        metrics[target] = regression_metrics(holdout[target], predicted)
    drift = {
        "note": "PSI compares input distributions. It does not measure prediction error or accuracy decay.",
        "features": {column: population_stability_index(train[column], holdout[column]) for column in NUMERIC_FEATURES},
    }
    performance = {
        "note": "These scores use holdout labels from the same synthetic generator. They are not factory performance.",
        "metrics": metrics,
    }
    report = {"drift": drift, "performance": performance}
    try:
        from evidently.metric_preset import DataDriftPreset
        from evidently.report import Report

        evidence = Report(metrics=[DataDriftPreset()])
        evidence.run(reference_data=train[NUMERIC_FEATURES], current_data=holdout[NUMERIC_FEATURES])
        html_path = ARTIFACTS / "evidently_drift.html"
        evidence.save_html(str(html_path))
        report["evidently_html"] = str(html_path)
    except Exception as exc:
        report["evidently_error"] = f"{exc.__class__.__name__}: {exc}"
    (ARTIFACTS / "evaluation.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    print(json.dumps(evaluate()["performance"]["metrics"]["total_cost"], indent=2))
