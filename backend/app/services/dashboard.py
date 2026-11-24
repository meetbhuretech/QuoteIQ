"""Dashboard aggregates from organization records. Empty inputs stay null."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.constants import SYNTHETIC_ORIGIN
from app.models import AuditLog, Drawing, Estimation, ManufacturingJob, Quotation, QuotationItem


def dashboard(db: Session, organization_id: UUID) -> dict:
    quotations = db.query(Quotation).filter(Quotation.organization_id == organization_id).all()
    drawings = db.query(Drawing).filter(Drawing.organization_id == organization_id).all()
    estimations = db.query(Estimation).filter(Estimation.organization_id == organization_id).all()
    items = (
        db.query(QuotationItem)
        .join(Quotation, Quotation.id == QuotationItem.quotation_id)
        .filter(Quotation.organization_id == organization_id)
        .all()
    )
    verified_jobs = (
        db.query(ManufacturingJob)
        .filter(
            ManufacturingJob.organization_id == organization_id,
            ManufacturingJob.verified.is_(True),
            ManufacturingJob.data_origin != SYNTHETIC_ORIGIN,
            ManufacturingJob.actual_cost.is_not(None),
            ManufacturingJob.estimated_cost.is_not(None),
        )
        .all()
    )
    durations = []
    for drawing in drawings:
        if drawing.processing_started_at and drawing.processing_completed_at:
            durations.append((drawing.processing_completed_at - drawing.processing_started_at).total_seconds())
    decided = [quote for quote in quotations if quote.status in {"approved", "sent", "accepted", "rejected"}]
    approved_like = [quote for quote in decided if quote.status in {"approved", "sent", "accepted"}]
    quoted_value = sum((quote.total_value or 0) for quote in quotations if quote.status != "rejected" and quote.total_value is not None)
    accuracy = _mape(verified_jobs)

    monthly: dict[str, int] = defaultdict(int)
    for quote in quotations:
        if quote.created_at is not None:
            monthly[quote.created_at.strftime("%Y-%m")] += 1
    materials: dict[str, float] = defaultdict(float)
    processes: dict[str, int] = defaultdict(int)
    for item in items:
        materials[item.material or "Unspecified"] += float(item.material_cost or 0)
        for process in item.processes or ["Unspecified"]:
            processes[process] += 1

    audits = (
        db.query(AuditLog)
        .filter(AuditLog.organization_id == organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(8)
        .all()
    )
    recent_quotes = sorted(quotations, key=lambda quote: quote.updated_at or quote.created_at, reverse=True)[:8]
    return {
        "total_quotation_requests": len(quotations),
        "pending_drawing_analysis": sum(1 for drawing in drawings if drawing.status not in {"estimated", "failed", "awaiting_verification"}),
        "awaiting_verification": sum(1 for drawing in drawings if drawing.status == "awaiting_verification"),
        "completed_estimations": len(estimations),
        "quotations_awaiting_approval": sum(1 for quote in quotations if quote.status == "awaiting_review"),
        "approved_quotations": sum(1 for quote in quotations if quote.status in {"approved", "sent", "accepted"}),
        "average_processing_seconds": round(sum(durations) / len(durations), 3) if durations else None,
        "total_estimated_quotation_value": round(float(quoted_value), 2) if quotations else 0,
        "estimation_accuracy_mape": accuracy["mape"],
        "estimation_accuracy_sample_size": accuracy["sample_size"],
        "accuracy_scope": "verified_operational_jobs_only",
        "approval_rate": (len(approved_like) / len(decided)) if decided else None,
        "monthly_volume": [{"month": key, "count": monthly[key]} for key in sorted(monthly)],
        "estimated_versus_actual": [
            {
                "part_name": job.part_name,
                "estimated_cost": float(job.estimated_cost),
                "actual_cost": float(job.actual_cost),
            }
            for job in verified_jobs
        ],
        "material_cost_distribution": [{"material": key, "cost": round(value, 2)} for key, value in materials.items()],
        "process_distribution": [{"process": key, "count": value} for key, value in processes.items()],
        "recent_quotations": [
            {"id": quote.id, "number": quote.number, "status": quote.status, "total_value": quote.total_value, "updated_at": quote.updated_at}
            for quote in recent_quotes
        ],
        "recent_activity": [
            {"id": audit.id, "action": audit.action, "entity_type": audit.entity_type, "entity_id": audit.entity_id, "created_at": audit.created_at}
            for audit in audits
        ],
    }


def _mape(jobs: list[ManufacturingJob]) -> dict:
    errors = []
    for job in jobs:
        actual = float(job.actual_cost)
        if actual == 0:
            continue
        errors.append(abs(actual - float(job.estimated_cost)) / abs(actual))
    if not errors:
        return {"mape": None, "sample_size": 0}
    return {"mape": round(sum(errors) / len(errors), 4), "sample_size": len(errors)}
