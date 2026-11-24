"""Model registry, quality gates, and promotion.

Training may register a candidate. Nothing in this module promotes a model
without an authorized person, and synthetic training cannot be marked production-ready.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domain.constants import FEATURE_COLUMNS, SYNTHETIC_LIMITATION, SYNTHETIC_ORIGIN
from app.models import ModelVersion, TrainingDataset
from app.services.audit import record_audit
from app.services.inference import artifact_health


def evaluate_gates(metrics: dict, row_count: int) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    total = (metrics or {}).get("total_cost") or {}
    if row_count < 500:
        reasons.append("Dataset has fewer than 500 rows.")
    r2 = total.get("r2")
    if r2 is None or r2 < 0.5:
        reasons.append("Holdout R² for total cost is below 0.5.")
    if total.get("mape_defined") and total.get("mape") is not None and total["mape"] > 50:
        reasons.append("Holdout MAPE for total cost is above 50%.")
    return not reasons, reasons


def import_local_candidate(db: Session, *, organization_id: UUID, actor_id: UUID, artifact_dir: str | None = None) -> ModelVersion:
    path = Path(artifact_dir or get_settings().model_artifact_dir).resolve()
    health = artifact_health(path)
    if not health["ok"]:
        raise AppError(422, health["reason"] or "Artifact is not healthy.")
    metadata = health["metadata"]
    version = str(metadata.get("version") or "unversioned")
    existing = (
        db.query(ModelVersion)
        .filter(ModelVersion.organization_id == organization_id, ModelVersion.version == version, ModelVersion.name == "quoteiq-cost")
        .first()
    )
    if existing:
        return existing
    synthetic = metadata.get("data_origin") == SYNTHETIC_ORIGIN
    dataset = TrainingDataset(
        organization_id=organization_id,
        name=metadata.get("dataset_name", "training-data"),
        version=version,
        origin=metadata.get("data_origin", "unknown"),
        row_count=int(metadata.get("row_count") or 0),
        storage_path=str(metadata.get("dataset_path") or ""),
        content_hash=metadata.get("dataset_hash"),
        metadata_json={"warning": metadata.get("warning"), "feature_columns": metadata.get("feature_columns")},
    )
    db.add(dataset)
    db.flush()
    model = ModelVersion(
        organization_id=organization_id,
        dataset_id=dataset.id,
        name="quoteiq-cost",
        version=version,
        target="cost_and_lead_time",
        algorithm=metadata.get("algorithm", "xgboost"),
        stage="candidate",
        metrics=metadata.get("metrics") or {},
        parameters=metadata.get("parameters") or {},
        artifact_path=str(path),
        is_synthetic_training=synthetic,
        production_ready=False,
        limitations=SYNTHETIC_LIMITATION if synthetic else metadata.get("warning", ""),
    )
    if metadata.get("feature_columns") != FEATURE_COLUMNS:
        raise AppError(422, "Refusing to import an artifact with a different feature contract.")
    db.add(model)
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        entity_type="model_version",
        entity_id=version,
        action="imported",
        after={"stage": "candidate", "synthetic": synthetic, "version": version},
    )
    db.commit()
    db.refresh(model)
    return model


def promote(db: Session, *, model: ModelVersion, actor_id: UUID, acknowledge_limitations: bool) -> ModelVersion:
    if model.is_synthetic_training and not acknowledge_limitations:
        raise AppError(422, "Synthetic models stay development-only until you acknowledge that limitation.")
    dataset_rows = 0
    if model.dataset_id:
        dataset = db.get(TrainingDataset, model.dataset_id)
        dataset_rows = dataset.row_count if dataset else 0
    passed, reasons = evaluate_gates(model.metrics or {}, dataset_rows)
    if not passed:
        raise AppError(422, "Quality gates failed: " + "; ".join(reasons))
    health = artifact_health(Path(model.artifact_path))
    if not health["ok"]:
        raise AppError(422, health["reason"] or "Artifact failed the health check.")
    current = (
        db.query(ModelVersion)
        .filter(ModelVersion.organization_id == model.organization_id, ModelVersion.stage == "active", ModelVersion.id != model.id)
        .all()
    )
    for item in current:
        item.stage = "archived"
    model.stage = "active"
    model.approved_by = actor_id
    model.approved_at = datetime.now(timezone.utc)
    model.production_ready = passed and not model.is_synthetic_training
    record_audit(
        db,
        organization_id=model.organization_id,
        actor_id=actor_id,
        entity_type="model_version",
        entity_id=str(model.id),
        action="promoted",
        after={"stage": "active", "production_ready": model.production_ready, "synthetic": model.is_synthetic_training},
    )
    db.commit()
    db.refresh(model)
    return model


def rollback(db: Session, *, model: ModelVersion, actor_id: UUID) -> ModelVersion:
    if model.stage == "rejected":
        raise AppError(409, "A rejected model cannot be rolled back into service.")
    others = (
        db.query(ModelVersion)
        .filter(ModelVersion.organization_id == model.organization_id, ModelVersion.id != model.id, ModelVersion.stage == "active")
        .all()
    )
    for item in others:
        item.stage = "archived"
    model.stage = "active"
    record_audit(
        db,
        organization_id=model.organization_id,
        actor_id=actor_id,
        entity_type="model_version",
        entity_id=str(model.id),
        action="rolled_back",
        after={"stage": "active"},
    )
    db.commit()
    db.refresh(model)
    return model


def local_experiments(artifact_dir: Path) -> list[dict]:
    path = artifact_dir / "experiments.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    for item in payload:
        item["source"] = "local_file"
    return payload


def mlflow_experiments() -> list[dict]:
    settings = get_settings()
    if not settings.mlflow_tracking_uri:
        return []
    try:
        import mlflow

        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        runs = mlflow.search_runs(max_results=20)
    except Exception:
        return []
    if runs is None or getattr(runs, "empty", True):
        return []
    records = []
    for _, row in runs.iterrows():
        records.append(
            {
                "source": "mlflow",
                "run_id": row.get("run_id"),
                "status": row.get("status"),
                "metrics": {key.replace("metrics.", ""): row[key] for key in row.index if str(key).startswith("metrics.")},
            }
        )
    return records
