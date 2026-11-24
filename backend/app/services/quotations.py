"""Quotation lifecycle. Sending requires a recorded human approval."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.serialize import jsonable
from app.domain.constants import STATUS_TRANSITIONS
from app.models import (
    ApprovalRecord,
    Customer,
    Drawing,
    Estimation,
    EstimationComponent,
    ExtractedSpecification,
    ManufacturingJob,
    Organization,
    OrganizationCostSettings,
    Quotation,
    QuotationItem,
)
from app.services.audit import record_audit
from app.services.estimation import create_estimation


def create_quotation(db: Session, *, organization_id: UUID, actor_id: UUID, customer_id: UUID, notes: str | None, validity_days: int | None) -> Quotation:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.organization_id != organization_id:
        raise AppError(404, "Customer not found.")
    settings = db.query(OrganizationCostSettings).filter(OrganizationCostSettings.organization_id == organization_id).one()
    days = validity_days or settings.default_validity_days
    quotation = Quotation(
        organization_id=organization_id,
        customer_id=customer.id,
        created_by=actor_id,
        number=_next_number(db, organization_id),
        status="draft",
        currency=settings.currency,
        validity_until=date.today() + timedelta(days=days),
        notes=notes,
        assumptions=[],
        missing_information=[],
    )
    db.add(quotation)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        entity_type="quotation",
        entity_id=str(quotation.id),
        action="created",
        after={"customer_id": str(customer.id), "number": quotation.number},
    )
    db.commit()
    db.refresh(quotation)
    return quotation


def attach_estimation(db: Session, *, quotation: Quotation, drawing: Drawing, actor_id: UUID) -> Estimation:
    if drawing.organization_id != quotation.organization_id:
        raise AppError(404, "Drawing not found.")
    drawing.quotation_id = quotation.id
    if drawing.customer_id is None:
        drawing.customer_id = quotation.customer_id
    db.commit()
    estimation = create_estimation(db, drawing=drawing, actor_id=actor_id)
    _upsert_item(db, quotation, drawing, estimation)
    _refresh_totals(db, quotation)
    record_audit(
        db,
        organization_id=quotation.organization_id,
        actor_id=actor_id,
        entity_type="quotation",
        entity_id=str(quotation.id),
        action="estimation_attached",
        after={"estimation_id": str(estimation.id), "total": quotation.total_value},
    )
    db.commit()
    db.refresh(quotation)
    return estimation


def transition(db: Session, *, quotation: Quotation, actor_id: UUID, action: str, comment: str | None) -> Quotation:
    target = {
        "approve": "approved",
        "reject": "rejected",
        "send": "sent",
        "accept": "accepted",
        "expire": "expired",
        "reopen": "draft",
    }.get(action)
    if target is None:
        raise AppError(422, "Unknown quotation action.")
    if target not in STATUS_TRANSITIONS.get(quotation.status, set()):
        raise AppError(409, f"Cannot {action} a quotation that is {quotation.status}.")
    if action == "reject" and not (comment and comment.strip()):
        raise AppError(422, "A rejection comment is required.")
    if action == "approve":
        _assert_ready(db, quotation)
    before = quotation.status
    quotation.status = target
    if action in {"approve", "reject"}:
        db.add(
            ApprovalRecord(
                organization_id=quotation.organization_id,
                quotation_id=quotation.id,
                action=action,
                comment=comment,
                actor_id=actor_id,
            )
        )
    if action == "accept":
        _create_jobs(db, quotation)
    record_audit(
        db,
        organization_id=quotation.organization_id,
        actor_id=actor_id,
        entity_type="quotation",
        entity_id=str(quotation.id),
        action=action,
        before={"status": before},
        after={"status": target, "comment": comment},
    )
    db.commit()
    db.refresh(quotation)
    return quotation


def render_pdf(db: Session, quotation: Quotation) -> bytes:
    organization = db.get(Organization, quotation.organization_id)
    customer = db.get(Customer, quotation.customer_id)
    items = db.query(QuotationItem).filter(QuotationItem.quotation_id == quotation.id).all()
    approved = quotation.status in {"approved", "sent", "accepted"}
    return _pdf(organization.name, customer, quotation, items, approved)


def _assert_ready(db: Session, quotation: Quotation) -> None:
    items = db.query(QuotationItem).filter(QuotationItem.quotation_id == quotation.id).all()
    if not items:
        raise AppError(422, "Add at least one estimated drawing before approval.")
    for item in items:
        spec = db.query(ExtractedSpecification).filter(ExtractedSpecification.drawing_id == item.drawing_id).one_or_none()
        if spec is None or spec.verification_status != "verified":
            raise AppError(422, "Every drawing on the quotation must be verified by an engineer.")
        if item.total is None or item.missing_information:
            raise AppError(422, "Every line needs a complete deterministic total and no missing information.")


def _upsert_item(db: Session, quotation: Quotation, drawing: Drawing, estimation: Estimation) -> None:
    spec = db.get(ExtractedSpecification, estimation.specification_id)
    components = db.query(EstimationComponent).filter(EstimationComponent.estimation_id == estimation.id, EstimationComponent.kind == "deterministic").all()
    by_code = {component.code: component.amount for component in components}
    additional_codes = ["scrap", "labor", "tooling", "packaging", "shipping", "overhead"]
    additional = None
    if all(by_code.get(code) is not None for code in additional_codes):
        additional = sum(by_code[code] for code in additional_codes)
    item = (
        db.query(QuotationItem)
        .filter(QuotationItem.quotation_id == quotation.id, QuotationItem.drawing_id == drawing.id)
        .one_or_none()
    )
    if item is None:
        item = QuotationItem(quotation_id=quotation.id, drawing_id=drawing.id, estimation_id=estimation.id, quantity=spec.quantity or 0)
        db.add(item)
    item.estimation_id = estimation.id
    item.part_name = spec.part_name
    item.drawing_reference = spec.drawing_number or drawing.original_filename
    item.material = spec.material
    item.processes = [spec.confirmed_process] if spec.confirmed_process else []
    item.quantity = spec.quantity or 0
    item.material_cost = by_code.get("material")
    item.machining_cost = by_code.get("machining")
    item.setup_cost = by_code.get("setup")
    item.finishing_cost = by_code.get("finishing")
    item.additional_cost = additional
    item.profit_amount = by_code.get("profit")
    item.total = estimation.deterministic_total
    item.production_hours = estimation.production_hours_deterministic
    item.lead_time_days = estimation.lead_time_days_deterministic
    item.assumptions = estimation.assumptions
    item.missing_information = estimation.missing_information
    item.confidence_low = estimation.confidence_low
    item.confidence_high = estimation.confidence_high
    item.ml_total_advisory = estimation.ml_total if estimation.ml_is_prediction else None


def _refresh_totals(db: Session, quotation: Quotation) -> None:
    db.flush()
    items = db.query(QuotationItem).filter(QuotationItem.quotation_id == quotation.id).all()
    if items and all(item.total is not None and not item.missing_information for item in items):
        quotation.total_value = sum((item.total for item in items), Decimal("0"))
        if quotation.status in {"draft", "processing", "approved", "rejected"}:
            quotation.status = "awaiting_review"
    else:
        quotation.total_value = None
    quotation.assumptions = [note for item in items for note in (item.assumptions or [])]
    quotation.missing_information = [note for item in items for note in (item.missing_information or [])]
    lows = [item.confidence_low for item in items if item.confidence_low is not None]
    highs = [item.confidence_high for item in items if item.confidence_high is not None]
    quotation.confidence_low = sum(lows, Decimal("0")) if lows and len(lows) == len(items) else None
    quotation.confidence_high = sum(highs, Decimal("0")) if highs and len(highs) == len(items) else None


def _create_jobs(db: Session, quotation: Quotation) -> None:
    items = db.query(QuotationItem).filter(QuotationItem.quotation_id == quotation.id).all()
    for item in items:
        spec = db.query(ExtractedSpecification).filter(ExtractedSpecification.drawing_id == item.drawing_id).one()
        estimation = db.get(Estimation, item.estimation_id)
        db.add(
            ManufacturingJob(
                organization_id=quotation.organization_id,
                quotation_id=quotation.id,
                drawing_id=item.drawing_id,
                part_name=item.part_name,
                drawing_number=item.drawing_reference,
                material_name=item.material,
                material_category=(estimation.explanation or {}).get("features", {}).get("material_category") if estimation else None,
                process=spec.confirmed_process,
                quantity=item.quantity,
                feature_vector=(estimation.explanation or {}).get("features") or {},
                estimated_cost=item.total,
                estimated_hours=item.production_hours,
                verified=False,
                training_candidate=False,
                data_origin="operations",
            )
        )


def _next_number(db: Session, organization_id: UUID) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"QI-{year}-"
    existing = db.query(Quotation).filter(Quotation.organization_id == organization_id, Quotation.number.like(f"{prefix}%")).count()
    return f"{prefix}{existing + 1:04d}"


def _pdf(org_name: str, customer: Customer, quotation: Quotation, items: list[QuotationItem], approved: bool) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    pdf.setFillColorRGB(0.043, 0.122, 0.227)
    pdf.rect(0, height - 70, width, 70, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Times-Bold", 18)
    pdf.drawString(36, height - 32, "QuoteIQ")
    pdf.setFont("Times-Roman", 10)
    pdf.drawString(36, height - 50, org_name)
    pdf.setFillColorRGB(0.1, 0.14, 0.2)
    pdf.setFont("Times-Bold", 14)
    pdf.drawString(36, height - 100, f"Quotation {quotation.number}")
    pdf.setFont("Times-Roman", 10)
    if not approved:
        pdf.setFillColorRGB(0.6, 0.25, 0.1)
        pdf.drawString(36, height - 116, "REVIEW COPY — not approved for sending")
        pdf.setFillColorRGB(0.1, 0.14, 0.2)
        y = height - 140
    else:
        y = height - 124
    pdf.drawString(36, y, f"Customer: {customer.company or customer.name}")
    pdf.drawString(36, y - 14, f"Status: {quotation.status}    Currency: {quotation.currency}    Valid until: {quotation.validity_until or '—'}")
    y -= 40
    pdf.setFont("Times-Bold", 10)
    pdf.drawString(36, y, "Part")
    pdf.drawString(220, y, "Qty")
    pdf.drawString(270, y, "Material")
    pdf.drawString(400, y, "Machining")
    pdf.drawString(480, y, "Total")
    y -= 8
    pdf.line(36, y, width - 36, y)
    pdf.setFont("Times-Roman", 9)
    for item in items:
        y -= 16
        if y < 120:
            pdf.showPage()
            y = height - 50
        pdf.drawString(36, y, (item.part_name or item.drawing_reference or "Part")[:28])
        pdf.drawString(220, y, str(item.quantity))
        pdf.drawString(270, y, _money(item.material_cost))
        pdf.drawString(400, y, _money(item.machining_cost))
        pdf.drawString(480, y, _money(item.total))
    y -= 28
    pdf.setFont("Times-Bold", 12)
    pdf.drawString(36, y, f"Quotation total: {_money(quotation.total_value)} {quotation.currency}")
    y -= 22
    pdf.setFont("Times-Roman", 8)
    pdf.drawString(36, y, "The total is the deterministic calculation from confirmed inputs and organization rates.")
    y -= 12
    advisory = [item.ml_total_advisory for item in items if item.ml_total_advisory is not None]
    if advisory:
        pdf.drawString(36, y, "An advisory model total exists and is not the commercial total. See the review workspace for its limitations.")
        y -= 12
    for note in (quotation.missing_information or [])[:6]:
        pdf.drawString(36, y, f"Missing: {note[:110]}")
        y -= 12
    for note in (quotation.assumptions or [])[:4]:
        pdf.drawString(36, y, f"Assumption: {note[:110]}")
        y -= 12
    if quotation.confidence_low is not None and quotation.confidence_high is not None:
        pdf.drawString(36, y, f"Model residual band (not a commercial tolerance): {_money(quotation.confidence_low)} to {_money(quotation.confidence_high)}")
    pdf.save()
    return buffer.getvalue()


def _money(value) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.2f}"


def record_actuals(db: Session, *, job: ManufacturingJob, actor_id: UUID, actual_cost: float, actual_hours: float | None, verified: bool) -> ManufacturingJob:
    before = {"actual_cost": job.actual_cost, "verified": job.verified}
    job.actual_cost = Decimal(str(actual_cost))
    job.actual_hours = None if actual_hours is None else Decimal(str(actual_hours))
    job.verified = verified
    if not verified:
        job.training_candidate = False
    record_audit(
        db,
        organization_id=job.organization_id,
        actor_id=actor_id,
        entity_type="manufacturing_job",
        entity_id=str(job.id),
        action="actuals_recorded",
        before=jsonable(before),
        after={"actual_cost": actual_cost, "actual_hours": actual_hours, "verified": verified},
    )
    db.commit()
    db.refresh(job)
    return job


def mark_training_candidate(db: Session, *, job: ManufacturingJob, actor_id: UUID) -> ManufacturingJob:
    if not job.verified or job.actual_cost is None:
        raise AppError(422, "Only verified jobs with an actual cost can become training candidates.")
    if job.data_origin == "synthetic_dev":
        raise AppError(422, "Synthetic rows cannot be marked as verified training candidates.")
    job.training_candidate = True
    record_audit(
        db,
        organization_id=job.organization_id,
        actor_id=actor_id,
        entity_type="manufacturing_job",
        entity_id=str(job.id),
        action="training_candidate",
        after={"training_candidate": True},
    )
    db.commit()
    db.refresh(job)
    return job
