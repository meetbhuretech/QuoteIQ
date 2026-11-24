"""Load an approved model artifact and score one feature row.

Training code is not imported here. If the artifact is missing or unhealthy,
the caller must use the deterministic cost engine and say so.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import pandas as pd

from app.domain.constants import COST_TARGETS, FEATURE_COLUMNS, LEAD_TIME_TARGET, SYNTHETIC_LIMITATION, SYNTHETIC_ORIGIN


class ModelNotAvailable(Exception):
    pass


def artifact_health(artifact_dir: Path) -> dict:
    metadata_path = artifact_dir / "metadata.json"
    if not metadata_path.exists():
        return {"ok": False, "reason": "metadata.json is missing", "metadata": None}
    metadata = json.loads(metadata_path.read_text())
    expected = metadata.get("feature_columns") or []
    missing = [target for target in [*COST_TARGETS, LEAD_TIME_TARGET] if not (artifact_dir / f"{target}.joblib").exists()]
    columns_ok = expected == FEATURE_COLUMNS
    reason = None
    if missing:
        reason = f"Missing model files: {', '.join(missing)}"
    elif not columns_ok:
        reason = "Artifact feature columns do not match the current feature contract."
    return {"ok": not missing and columns_ok, "reason": reason, "metadata": metadata, "missing": missing}


def predict(artifact_dir: Path, features: dict) -> dict:
    health = artifact_health(artifact_dir)
    if not health["ok"]:
        raise ModelNotAvailable(health["reason"] or "Model artifact is not healthy")
    import joblib

    metadata = health["metadata"]
    frame = pd.DataFrame([{column: features[column] for column in FEATURE_COLUMNS}])
    started = time.perf_counter()
    predictions = {}
    for target in [*COST_TARGETS, LEAD_TIME_TARGET]:
        model = joblib.load(artifact_dir / f"{target}.joblib")
        raw = float(model.predict(frame)[0])
        predictions[target] = _original_units(raw, metadata)
    latency_ms = (time.perf_counter() - started) * 1000
    total_metrics = (metadata.get("metrics") or {}).get("total_cost") or {}
    mae = total_metrics.get("mae")
    interval = None
    if isinstance(mae, (int, float)):
        interval = {
            "low": predictions["total_cost"] - mae,
            "high": predictions["total_cost"] + mae,
            "meaning": "Holdout mean absolute error band around the total-cost prediction. This is not a calibrated statistical interval.",
        }
    synthetic = metadata.get("data_origin") == SYNTHETIC_ORIGIN
    return {
        "predictions": predictions,
        "latency_ms": round(latency_ms, 3),
        "metadata": metadata,
        "interval": interval,
        "explanation": _explain(artifact_dir, frame, metadata),
        "disclaimer": metadata.get("warning") or (SYNTHETIC_LIMITATION if synthetic else "Model limitations are stored on the model version."),
        "is_synthetic": synthetic,
    }


def _original_units(raw: float, metadata: dict) -> float:
    transform = (metadata.get("parameters") or {}).get("target_transform")
    if transform == "log1p":
        return max(0.0, math.expm1(raw))
    return raw


def _explain(artifact_dir: Path, frame: pd.DataFrame, metadata: dict) -> dict:
    try:
        import joblib
        import shap

        model = joblib.load(artifact_dir / "total_cost.joblib")
        transformed = model.named_steps["preprocess"].transform(frame)
        explainer = shap.TreeExplainer(model.named_steps["model"])
        values = explainer.shap_values(transformed)
        row = values[0] if hasattr(values, "__len__") else values
        names = _transformed_names(model)
        pairs = sorted(
            ({"feature": names[index] if index < len(names) else f"f{index}", "shap": float(value)} for index, value in enumerate(row)),
            key=lambda item: abs(item["shap"]),
            reverse=True,
        )
        result = {"method": "shap", "top_features": pairs[:8]}
        if (metadata.get("parameters") or {}).get("target_transform") == "log1p":
            result["scale"] = "Contributions are on the log1p target, not in currency."
        return result
    except Exception as exc:
        gain = _gain_importance(artifact_dir)
        if gain:
            result = {"method": "gain_importance", "top_features": gain, "shap_error": exc.__class__.__name__}
            if (metadata.get("parameters") or {}).get("target_transform") == "log1p":
                result["scale"] = "Importance is from the log1p model, not a currency contribution."
            return result
        return {"method": "unavailable", "reason": str(exc)}


def _transformed_names(model) -> list[str]:
    try:
        return list(model.named_steps["preprocess"].get_feature_names_out())
    except Exception:
        return FEATURE_COLUMNS


def _gain_importance(artifact_dir: Path) -> list[dict]:
    try:
        import joblib

        model = joblib.load(artifact_dir / "total_cost.joblib")
        booster = model.named_steps["model"].get_booster()
        scores = booster.get_score(importance_type="gain")
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:8]
        return [{"feature": name, "gain": float(value)} for name, value in ranked]
    except Exception:
        return []
