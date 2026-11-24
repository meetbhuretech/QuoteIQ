"""Create an estimation from a verified specification.

Deterministic lines and model output are stored separately. A missing model
produces a labelled fallback and never a fabricated prediction.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.serialize import jsonable
from app.domain.constants import SYNTHETIC_LIMITATION
from app.models import (
    Drawing,
    Estimation,
    EstimationComponent,
    ExtractedEvidence,
    ExtractedSpecification,
    MachineRate,
    ManufacturingProcess,
    Material,
    MaterialPrice,
    ModelVersion,
    OrganizationCostSettings,
    PredictionLog,
)
from app.services.audit import record_audit
from app.services.cost_engine import CostInput, calculate_cost
from app.services.features import build_features, bounding_volume_cm3, to_millimetres
from app.services.inference import ModelNotAvailable, predict

FALLBACK_DISCLAIMER = (
    "No active model was used. Amounts in the deterministic section are calculated from "
    "organization rates and confirmed inputs. They are not machine-learning predictions."
)


def critical_missing(spec: ExtractedSpecification) -> list[str]:
    missing = []
    if spec.material_id is None:
        missing.append("material")
    if spec.units not in {"mm", "in"}:
        missing.append("units")
    if spec.quantity is None or spec.quantity < 1:
        missing.append("quantity")
    if not spec.confirmed_process:
        missing.append("manufacturing_process")
    has_box = spec.length is not None and spec.width is not None and spec.height is not None
    if spec.confirmed_volume_cm3 is None and not has_box:
        missing.append("volume_or_dimensions")
    if spec.confirmed_machine_hours is None:
        missing.append("machine_hours")
    if spec.confirmed_setup_hours is None:
        missing.append("setup_hours")
    if spec.confirmed_hole_count is None:
        missing.append("hole_count")
    if spec.confirmed_feature_count is None:
        missing.append("feature_count")
    if spec.finishing_required is None:
        missing.append("finishing_required")
    if spec.finishing_required and spec.confirmed_finishing_hours is None:
        missing.append("finishing_hours")
    return missing


def verify_specification(db: Session, *, spec: ExtractedSpecification, actor_id: UUID, payload: dict) -> ExtractedSpecification:
    before = _spec_snapshot(spec)
    changed = False
    editable = [
        "part_name",
        "drawing_number",
        "units",
        "length",
        "width",
        "height",
        "diameter",
        "thickness",
        "surface_finish",
        "quantity",
        "confirmed_process",
        "confirmed_machine_category",
        "confirmed_machine_hours",
        "confirmed_setup_hours",
        "confirmed_hole_count",
        "confirmed_feature_count",
        "confirmed_volume_cm3",
        "confirmed_setup_complexity",
        "confirmed_finishing_hours",
        "finishing_required",
        "tolerances",
        "manufacturing_notes",
    ]
    for field in editable:
        if field in payload and payload[field] is not None:
            value = payload[field]
            if field in {"length", "width", "height", "diameter", "thickness", "confirmed_machine_hours", "confirmed_setup_hours", "confirmed_volume_cm3", "confirmed_finishing_hours"}:
                value = Decimal(str(value))
            setattr(spec, field, value)
            changed = True
            _human_evidence(db, spec, field, value, actor_id)
    if payload.get("material_id") is not None:
        material = db.get(Material, payload["material_id"])
        if material is None or material.organization_id != spec.organization_id or not material.is_active:
            raise AppError(404, "Material not found in this organization.")
        spec.material_id = material.id
        spec.material = material.name
        changed = True
        _human_evidence(db, spec, "material", material.name, actor_id)
    if changed and not payload.get("mark_verified"):
        spec.verification_status = "unverified"
        spec.verified_by = None
        spec.verified_at = None
    if spec.confirmed_process and not spec.confirmed_machine_category:
        spec.confirmed_machine_category = spec.confirmed_process
    spec.missing_information = critical_missing(spec)
    if payload.get("mark_verified"):
        if spec.missing_information:
            raise AppError(422, "Verification is blocked until required fields are confirmed: " + ", ".join(spec.missing_information))
        spec.verification_status = "verified"
        spec.verified_by = actor_id
        spec.verified_at = datetime.now(timezone.utc)
        spec.missing_information = []
    record_audit(
        db,
        organization_id=spec.organization_id,
        actor_id=actor_id,
        entity_type="extracted_specification",
        entity_id=str(spec.id),
        action="verified" if spec.verification_status == "verified" else "corrected",
        before=before,
        after={**_spec_snapshot(spec), "note": payload.get("note")},
    )
    db.commit()
    db.refresh(spec)
    return spec


def create_estimation(db: Session, *, drawing: Drawing, actor_id: UUID) -> Estimation:
    spec = db.query(ExtractedSpecification).filter(ExtractedSpecification.drawing_id == drawing.id).one_or_none()
    if spec is None:
        raise AppError(409, "This drawing has no extracted specification yet.")
    if spec.verification_status != "verified":
        raise AppError(422, "An engineer must verify the specification before estimation.")
    remaining = critical_missing(spec)
    if remaining:
        raise AppError(422, "Estimation is blocked until required fields are confirmed: " + ", ".join(remaining))

    material = db.get(Material, spec.material_id)
    price = _latest_price(db, material.id)
    if price is None:
        raise AppError(422, "The selected material has no price. Add a price before estimating.")
    settings = db.query(OrganizationCostSettings).filter(OrganizationCostSettings.organization_id == drawing.organization_id).one()
    rate = _rate(db, drawing.organization_id, spec.confirmed_process)
    if rate is None:
        raise AppError(422, f"No machine rate is configured for {spec.confirmed_process}.")
    finishing_rate = _rate(db, drawing.organization_id, "finishing") if spec.finishing_required else None
    if spec.finishing_required and finishing_rate is None:
        raise AppError(422, "Finishing is required and no finishing rate is configured.")

    length_mm = to_millimetres(float(spec.length), spec.units) if spec.length is not None else None
    width_mm = to_millimetres(float(spec.width), spec.units) if spec.width is not None else None
    height_mm = to_millimetres(float(spec.height), spec.units) if spec.height is not None else None
    volume = float(spec.confirmed_volume_cm3) if spec.confirmed_volume_cm3 is not None else None
    if volume is None and None not in {length_mm, width_mm, height_mm}:
        volume = bounding_volume_cm3(length_mm, width_mm, height_mm, float(settings.stock_fill_ratio))

    cost = calculate_cost(
        CostInput(
            quantity=int(spec.quantity),
            volume_cm3=volume,
            density_g_cm3=float(material.density),
            unit_price_per_kg=float(price.unit_price),
            stock_fill_ratio=float(settings.stock_fill_ratio),
            scrap_allowance_pct=float(settings.scrap_allowance_pct),
            machine_hours_per_piece=float(spec.confirmed_machine_hours),
            machine_hourly_rate=float(rate.hourly_rate),
            setup_hours=float(spec.confirmed_setup_hours),
            setup_hourly_rate=float(rate.setup_hourly_rate),
            finishing_required=bool(spec.finishing_required),
            finishing_hourly_rate=None if finishing_rate is None else float(finishing_rate.hourly_rate),
            finishing_hours=None if spec.confirmed_finishing_hours is None else float(spec.confirmed_finishing_hours),
            tooling_cost=float(settings.tooling_cost),
            labor_hourly_rate=float(settings.labor_hourly_rate),
            overhead_pct=float(settings.overhead_pct),
            packaging_cost=float(settings.packaging_cost),
            shipping_cost=float(settings.shipping_cost),
            profit_margin_pct=float(settings.profit_margin_pct),
            hours_per_day=float(settings.hours_per_day),
            shipping_days=int(settings.shipping_days),
        )
    )
    features, feature_missing, feature_assumptions = build_features(
        material_category=material.category,
        density=float(material.density),
        units=spec.units,
        length=None if spec.length is None else float(spec.length),
        width=None if spec.width is None else float(spec.width),
        height=None if spec.height is None else float(spec.height),
        quantity=spec.quantity,
        process=spec.confirmed_process,
        machine_category=spec.confirmed_machine_category,
        hole_count=spec.confirmed_hole_count,
        feature_count=spec.confirmed_feature_count,
        tolerance_count=len(spec.tolerances or []),
        finishing_required=spec.finishing_required,
        setup_complexity=spec.confirmed_setup_complexity,
        volume_cm3=float(spec.confirmed_volume_cm3) if spec.confirmed_volume_cm3 is not None else None,
        stock_fill_ratio=float(settings.stock_fill_ratio),
    )

    active = (
        db.query(ModelVersion)
        .filter(ModelVersion.organization_id == drawing.organization_id, ModelVersion.stage == "active")
        .order_by(ModelVersion.approved_at.desc())
        .first()
    )
    ml_payload = None
    fallback = None
    model_version_id = None
    if features is None:
        fallback = "Model inputs are incomplete: " + ", ".join(feature_missing)
    elif active is None:
        fallback = "This organization has no active model. Import and promote a candidate before requesting a prediction."
    else:
        try:
            from pathlib import Path

            ml_payload = predict(Path(active.artifact_path), features)
            model_version_id = active.id
        except ModelNotAvailable as exc:
            fallback = str(exc)
        except Exception as exc:
            fallback = f"The active model failed to score this part: {exc}"

    estimation = Estimation(
        organization_id=drawing.organization_id,
        drawing_id=drawing.id,
        specification_id=spec.id,
        quotation_id=drawing.quotation_id,
        model_version_id=model_version_id,
        created_by=actor_id,
        deterministic_total=_dec(cost.total),
        deterministic_complete=cost.total_complete,
        ml_total=_dec(ml_payload["predictions"]["total_cost"]) if ml_payload else None,
        ml_is_prediction=ml_payload is not None,
        fallback_reason=fallback,
        production_hours_deterministic=_dec(cost.production_hours),
        production_hours_ml=_dec(ml_payload["predictions"]["production_hours"]) if ml_payload else None,
        lead_time_days_deterministic=_dec(cost.lead_time_days),
        lead_time_days_ml=_dec(ml_payload["predictions"]["lead_time_days"]) if ml_payload else None,
        confidence_low=_dec(ml_payload["interval"]["low"]) if ml_payload and ml_payload.get("interval") else None,
        confidence_high=_dec(ml_payload["interval"]["high"]) if ml_payload and ml_payload.get("interval") else None,
        assumptions=cost.assumptions + feature_assumptions,
        missing_information=cost.missing,
        explanation={
            "features": features,
            "model": None
            if ml_payload is None
            else {
                "version": (ml_payload["metadata"] or {}).get("version"),
                "data_origin": (ml_payload["metadata"] or {}).get("data_origin"),
                "metrics": (ml_payload["metadata"] or {}).get("metrics"),
                "interval": ml_payload.get("interval"),
                "predictions": ml_payload["predictions"],
                "is_synthetic": ml_payload["is_synthetic"],
            },
            "shap_or_importance": None if ml_payload is None else ml_payload.get("explanation"),
        },
        disclaimer=ml_payload["disclaimer"] if ml_payload else FALLBACK_DISCLAIMER,
    )
    if ml_payload and ml_payload["is_synthetic"]:
        estimation.disclaimer = SYNTHETIC_LIMITATION
    db.add(estimation)
    db.flush()
    for line in cost.lines:
        db.add(
            EstimationComponent(
                estimation_id=estimation.id,
                kind="deterministic",
                code=line.code,
                label=line.label,
                amount=_dec(line.amount),
                formula=line.formula,
                inputs=jsonable(line.inputs),
                complete=line.complete,
            )
        )
    if ml_payload:
        for code, amount in ml_payload["predictions"].items():
            db.add(
                EstimationComponent(
                    estimation_id=estimation.id,
                    kind="ml",
                    code=code,
                    label=f"Model advisory: {code.replace('_', ' ')}",
                    amount=_dec(amount),
                    formula="XGBoost prediction from the active model artifact. Not used as the quotation total unless an engineer adopts a value explicitly.",
                    inputs={"feature_columns": list(features)},
                    complete=True,
                )
            )
    db.add(
        PredictionLog(
            organization_id=drawing.organization_id,
            model_version_id=model_version_id,
            estimation_id=estimation.id,
            latency_ms=0 if ml_payload is None else ml_payload["latency_ms"],
            is_fallback=ml_payload is None,
            input_hash=hashlib.sha256(json.dumps(features, sort_keys=True, default=str).encode()).hexdigest(),
            output={"fallback_reason": fallback, "predictions": None if ml_payload is None else ml_payload["predictions"]},
        )
    )
    if cost.total_complete:
        drawing.status = "estimated"
        history = list(drawing.stage_history or [])
        history.append({"stage": "estimated", "at": datetime.now(timezone.utc).isoformat(), "note": "Deterministic estimation completed. Model output is advisory."})
        drawing.stage_history = history
    record_audit(
        db,
        organization_id=drawing.organization_id,
        actor_id=actor_id,
        entity_type="estimation",
        entity_id=str(estimation.id),
        action="created",
        after={"deterministic_total": cost.total, "ml_is_prediction": ml_payload is not None, "fallback_reason": fallback},
    )
    db.commit()
    db.refresh(estimation)
    return estimation


def _latest_price(db: Session, material_id: UUID) -> MaterialPrice | None:
    return (
        db.query(MaterialPrice)
        .filter(MaterialPrice.material_id == material_id)
        .order_by(MaterialPrice.effective_date.desc(), MaterialPrice.created_at.desc())
        .first()
    )


def _rate(db: Session, organization_id: UUID, category: str) -> MachineRate | None:
    process = (
        db.query(ManufacturingProcess)
        .filter(ManufacturingProcess.organization_id == organization_id, ManufacturingProcess.category == category)
        .first()
    )
    if process is None:
        return None
    return (
        db.query(MachineRate)
        .filter(MachineRate.organization_id == organization_id, MachineRate.process_id == process.id)
        .order_by(MachineRate.effective_date.desc(), MachineRate.created_at.desc())
        .first()
    )


def _human_evidence(db: Session, spec: ExtractedSpecification, field: str, value, actor_id: UUID) -> None:
    db.add(
        ExtractedEvidence(
            organization_id=spec.organization_id,
            specification_id=spec.id,
            drawing_id=spec.drawing_id,
            field_name=field,
            value_text=str(value),
            source_document="human_verification",
            location=f"user {actor_id}",
            method="human_entry",
            confidence=Decimal("1.0000"),
            verification_status="verified",
        )
    )


def _spec_snapshot(spec: ExtractedSpecification) -> dict:
    return jsonable(
        {
            "part_name": spec.part_name,
            "material": spec.material,
            "material_id": spec.material_id,
            "units": spec.units,
            "length": spec.length,
            "width": spec.width,
            "height": spec.height,
            "quantity": spec.quantity,
            "confirmed_process": spec.confirmed_process,
            "confirmed_machine_hours": spec.confirmed_machine_hours,
            "verification_status": spec.verification_status,
        }
    )


def _dec(value):
    if value is None:
        return None
    return Decimal(str(round(float(value), 4)))
