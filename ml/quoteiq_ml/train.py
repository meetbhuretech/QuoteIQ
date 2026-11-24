"""Train baseline and XGBoost models. This module is not imported by the API."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

from quoteiq_ml.metrics import from_log1p, regression_metrics
from quoteiq_ml.spec import CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES, SYNTHETIC_ORIGIN, TARGETS, WARNING
from quoteiq_ml.synthetic import write_dataset

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets" / "synthetic_dev.csv"
ARTIFACTS = ROOT / "artifacts"


def build_pipeline(kind: str, estimators: int = 80) -> Pipeline:
    preprocess = ColumnTransformer(
        [
            ("num", "passthrough", NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
        ]
    )
    if kind == "xgboost":
        model = XGBRegressor(
            n_estimators=estimators,
            max_depth=4,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="reg:squarederror",
            random_state=42,
            n_jobs=2,
        )
    elif kind == "linear":
        model = LinearRegression()
    elif kind == "hist_gradient_boosting":
        model = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.08, max_iter=estimators, random_state=42)
    else:
        raise ValueError(kind)
    return Pipeline([("preprocess", preprocess), ("model", model)])


def split_by_family(frame: pd.DataFrame):
    families = sorted(frame["family_id"].unique())
    train_cut = int(len(families) * 0.7)
    valid_cut = int(len(families) * 0.85)
    train_ids = set(families[:train_cut])
    valid_ids = set(families[train_cut:valid_cut])
    test_ids = set(families[valid_cut:])
    return (
        frame[frame["family_id"].isin(train_ids)],
        frame[frame["family_id"].isin(valid_ids)],
        frame[frame["family_id"].isin(test_ids)],
    )


def train(families: int = 800, rows_per_family: int = 4, estimators: int = 80) -> dict:
    frame = write_dataset(DATASET, families=families, rows_per_family=rows_per_family)
    train_df, valid_df, test_df = split_by_family(frame)
    overlap = set(train_df["family_id"]) & set(test_df["family_id"])
    if overlap:
        raise RuntimeError("Family leakage between train and test.")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    test_df.to_csv(ARTIFACTS / "holdout.csv", index=False)
    train_df.to_csv(ARTIFACTS / "train_split.csv", index=False)
    metrics = {"xgboost": {}, "linear": {}, "hist_gradient_boosting": {}}
    parameters = {
        "n_estimators": estimators,
        "max_depth": 4,
        "learning_rate": 0.08,
        "split": "family_id",
        "target_transform": "log1p",
        "reported_metrics": "original units after expm1, clipped at zero",
    }
    for target in TARGETS:
        labels = np.log1p(np.clip(train_df[target].to_numpy(dtype=float), 0, None))
        model = build_pipeline("xgboost", estimators)
        model.fit(train_df[FEATURE_COLUMNS], labels)
        joblib.dump(model, ARTIFACTS / f"{target}.joblib")
        metrics["xgboost"][target] = regression_metrics(
            test_df[target], from_log1p(model.predict(test_df[FEATURE_COLUMNS]))
        )
        for baseline in ("linear", "hist_gradient_boosting"):
            baseline_model = build_pipeline(baseline, estimators)
            baseline_model.fit(train_df[FEATURE_COLUMNS], labels)
            metrics[baseline][target] = regression_metrics(
                test_df[target], from_log1p(baseline_model.predict(test_df[FEATURE_COLUMNS]))
            )
    digest = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    metadata = {
        "version": version,
        "data_origin": SYNTHETIC_ORIGIN,
        "warning": WARNING,
        "dataset_name": "synthetic_dev",
        "dataset_path": str(DATASET),
        "dataset_hash": digest,
        "row_count": int(len(frame)),
        "train_rows": int(len(train_df)),
        "validation_rows": int(len(valid_df)),
        "test_rows": int(len(test_df)),
        "feature_columns": FEATURE_COLUMNS,
        "algorithm": "xgboost",
        "parameters": parameters,
        "metrics": _served_metrics(metrics),
        "baseline_metrics": {"linear": metrics["linear"], "hist_gradient_boosting": metrics["hist_gradient_boosting"]},
        "production_ready": False,
        "limitations": [
            "Labels come from a formula, not measured shop cost.",
            "Each regressor is fit to log1p of its target. MAE, RMSE, R², and MAPE are computed after expm1, in the original units.",
            "Do not promote this artifact to a production-certified model.",
        ],
    }
    (ARTIFACTS / "metadata.json").write_text(json.dumps(metadata, indent=2))
    experiments_path = ARTIFACTS / "experiments.json"
    experiments = json.loads(experiments_path.read_text()) if experiments_path.exists() else []
    experiments.append({"version": version, "metrics": metadata["metrics"], "baseline_metrics": metadata["baseline_metrics"], "row_count": metadata["row_count"], "data_origin": SYNTHETIC_ORIGIN})
    experiments_path.write_text(json.dumps(experiments, indent=2))
    _log_mlflow(metadata)
    return metadata


def _served_metrics(metrics: dict) -> dict:
    return metrics["xgboost"]


def _log_mlflow(metadata: dict) -> None:
    tracking = __import__("os").environ.get("MLFLOW_TRACKING_URI")
    if not tracking:
        return
    try:
        import mlflow

        mlflow.set_tracking_uri(tracking)
        mlflow.set_experiment("quoteiq-synthetic-dev")
        with mlflow.start_run(run_name=metadata["version"]):
            mlflow.log_params(metadata["parameters"])
            mlflow.set_tag("data_origin", SYNTHETIC_ORIGIN)
            mlflow.set_tag("warning", metadata["warning"])
            for target, values in metadata["metrics"].items():
                for name, value in values.items():
                    if isinstance(value, float):
                        mlflow.log_metric(f"{target}_{name}", value)
            mlflow.log_dict(metadata, "metadata.json")
    except Exception as exc:
        print(f"MLflow logging skipped: {exc}")


if __name__ == "__main__":
    result = train()
    print(json.dumps({"version": result["version"], "row_count": result["row_count"], "total_cost": result["metrics"]["total_cost"]}, indent=2))
