"""HTTP API for QuoteIQ. Handlers validate and delegate."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal, require_roles, scoped
from app.core.errors import AppError
from app.core.serialize import jsonable
from app.db.session import get_db
from app.domain.constants import PROCESSES
from app.models import (
    ApprovalRecord,
    AuditLog,
    Customer,
    Drawing,
    DrawingPage,
    Estimation,
    EstimationComponent,
    ExtractedEvidence,
    ExtractedSpecification,
    Machine,
    MachineRate,
    ManufacturingJob,
    ManufacturingProcess,
    Material,
    MaterialPrice,
    ModelVersion,
    OrganizationCostSettings,
    OrganizationMember,
    Quotation,
    QuotationItem,
    User,
)
from app.services.accounts import add_member, login, register, switch_organization
from app.services.audit import record_audit
from app.services.dashboard import dashboard
from app.services.estimation import create_estimation, verify_specification
from app.services.model_registry import import_local_candidate, local_experiments, mlflow_experiments, promote, rollback
from app.services.org_seed import SAMPLE_NOTE
from app.services.pipeline import create_drawing, process_drawing
from app.services.quotations import attach_estimation, create_quotation, mark_training_candidate, record_actuals, render_pdf, transition
from app.services.similarity import cluster_jobs, search_jobs, similar_jobs
from app.services.storage import get_storage
from app.services.inference import artifact_health
from pathlib import Path

router = APIRouter(prefix="/api/v1")
reader = require_roles("manufacturing_engineer", "sales_manager", "quotation_reviewer")
engineer = require_roles("manufacturing_engineer")
sales = require_roles("sales_manager", "manufacturing_engineer")
reviewer = require_roles("quotation_reviewer")
admin = require_roles()


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str = Field(min_length=2, max_length=200)
    organization_name: str = Field(min_length=2, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class SwitchIn(BaseModel):
    organization_id: UUID


class MemberIn(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: str


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    notes: str | None = None


class QuotationIn(BaseModel):
    customer_id: UUID
    notes: str | None = None
    validity_days: int | None = Field(default=None, ge=1, le=365)


class ActionIn(BaseModel):
    comment: str | None = None


class EstimateIn(BaseModel):
    drawing_id: UUID


class VerifyIn(BaseModel):
    part_name: str | None = None
    drawing_number: str | None = None
    material_id: UUID | None = None
    units: str | None = None
    length: float | None = None
    width: float | None = None
    height: float | None = None
    diameter: float | None = None
    thickness: float | None = None
    tolerances: list[str] | None = None
    surface_finish: str | None = None
    quantity: int | None = Field(default=None, ge=1)
    manufacturing_notes: list[str] | None = None
    confirmed_process: str | None = None
    confirmed_machine_category: str | None = None
    confirmed_machine_hours: float | None = Field(default=None, ge=0)
    confirmed_setup_hours: float | None = Field(default=None, ge=0)
    confirmed_hole_count: int | None = Field(default=None, ge=0)
    confirmed_feature_count: int | None = Field(default=None, ge=0)
    confirmed_volume_cm3: float | None = Field(default=None, gt=0)
    confirmed_setup_complexity: int | None = Field(default=None, ge=1, le=5)
    confirmed_finishing_hours: float | None = Field(default=None, ge=0)
    finishing_required: bool | None = None
    mark_verified: bool = False
    note: str | None = None


class MaterialIn(BaseModel):
    name: str
    category: str
    density: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    currency: str = "USD"
    supplier: str | None = None
    availability: str = "unknown"
    notes: str | None = None


class MaterialPatch(BaseModel):
    density: float | None = Field(default=None, gt=0)
    availability: str | None = None
    notes: str | None = None
    is_active: bool | None = None
    unit_price: float | None = Field(default=None, ge=0)
    currency: str | None = None
    supplier: str | None = None


class SettingsIn(BaseModel):
    currency: str | None = None
    scrap_allowance_pct: float | None = Field(default=None, ge=0)
    tooling_cost: float | None = Field(default=None, ge=0)
    labor_hourly_rate: float | None = Field(default=None, ge=0)
    overhead_pct: float | None = Field(default=None, ge=0)
    packaging_cost: float | None = Field(default=None, ge=0)
    shipping_cost: float | None = Field(default=None, ge=0)
    profit_margin_pct: float | None = Field(default=None, ge=0)
    default_setup_hours: float | None = Field(default=None, ge=0)
    hours_per_day: float | None = Field(default=None, gt=0)
    shipping_days: int | None = Field(default=None, ge=0)
    stock_fill_ratio: float | None = Field(default=None, gt=0, le=1)
    default_validity_days: int | None = Field(default=None, ge=1, le=365)


class RateIn(BaseModel):
    process_category: str
    hourly_rate: float = Field(ge=0)
    setup_hourly_rate: float = Field(ge=0)


class ActualsIn(BaseModel):
    actual_cost: float = Field(ge=0)
    actual_hours: float | None = Field(default=None, ge=0)
    verified: bool = False


class PromoteIn(BaseModel):
    acknowledge_limitations: bool = False


def page_args(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> tuple[int, int]:
    return page, page_size


def _page(query, page: int, page_size: int) -> dict:
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.post("/auth/register")
def register_route(body: RegisterIn, db: Session = Depends(get_db)):
    return jsonable(register(db, email=body.email, password=body.password, full_name=body.full_name, organization_name=body.organization_name))


@router.post("/auth/login")
def login_route(body: LoginIn, db: Session = Depends(get_db)):
    return jsonable(login(db, email=body.email, password=body.password))


@router.post("/auth/logout")
def logout_route(_: Principal = Depends(get_principal)):
    return {"detail": "Discard the bearer token on the client. Tokens are not stored server-side."}


@router.get("/auth/me")
def me_route(principal: Principal = Depends(get_principal)):
    return jsonable(
        {
            "user": {"id": principal.user.id, "email": principal.user.email, "full_name": principal.user.full_name, "is_super_admin": principal.user.is_super_admin},
            "organization": None
            if principal.organization is None
            else {"id": principal.organization.id, "name": principal.organization.name, "slug": principal.organization.slug},
            "role": principal.role,
        }
    )


@router.post("/auth/switch-organization")
def switch_route(body: SwitchIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return jsonable(switch_organization(db, user=principal.user, organization_id=body.organization_id))


@router.get("/organizations/current")
def current_org(principal: Principal = Depends(reader)):
    return jsonable({"id": principal.organization.id, "name": principal.organization.name, "slug": principal.organization.slug, "role": principal.role})


@router.get("/organizations/members")
def list_members(principal: Principal = Depends(admin), db: Session = Depends(get_db)):
    rows = (
        db.query(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .filter(OrganizationMember.organization_id == principal.organization_id)
        .all()
    )
    return jsonable([{"user_id": user.id, "email": user.email, "full_name": user.full_name, "role": member.role} for member, user in rows])


@router.post("/organizations/members", status_code=201)
def create_member(body: MemberIn, principal: Principal = Depends(admin), db: Session = Depends(get_db)):
    member = add_member(
        db,
        organization_id=principal.organization_id,
        actor_id=principal.user.id,
        email=body.email,
        full_name=body.full_name,
        password=body.password,
        role=body.role,
    )
    return jsonable({"id": member.id, "user_id": member.user_id, "role": member.role})


@router.get("/customers")
def list_customers(q: str | None = None, paging: tuple[int, int] = Depends(page_args), principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    query = db.query(Customer).filter(Customer.organization_id == principal.organization_id)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter((Customer.name.ilike(like)) | (Customer.company.ilike(like)))
    payload = _page(query.order_by(Customer.created_at.desc()), *paging)
    payload["items"] = jsonable(payload["items"])
    return payload


@router.post("/customers", status_code=201)
def create_customer(body: CustomerIn, principal: Principal = Depends(sales), db: Session = Depends(get_db)):
    customer = Customer(organization_id=principal.organization_id, **body.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return jsonable(customer)


@router.get("/customers/{customer_id}")
def get_customer(customer_id: UUID, principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    return jsonable(scoped(db, Customer, principal.organization_id, customer_id))


@router.patch("/customers/{customer_id}")
def patch_customer(customer_id: UUID, body: CustomerIn, principal: Principal = Depends(sales), db: Session = Depends(get_db)):
    customer = scoped(db, Customer, principal.organization_id, customer_id)
    for key, value in body.model_dump().items():
        setattr(customer, key, value)
    db.commit()
    db.refresh(customer)
    return jsonable(customer)


@router.get("/dashboard")
def dashboard_route(principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    return jsonable(dashboard(db, principal.organization_id))


@router.post("/drawings/upload", status_code=201)
async def upload_drawing(
    file: UploadFile = File(...),
    customer_id: UUID | None = Form(default=None),
    quotation_id: UUID | None = Form(default=None),
    principal: Principal = Depends(sales),
    db: Session = Depends(get_db),
):
    data = await file.read()
    drawing = create_drawing(
        db,
        organization_id=principal.organization_id,
        actor_id=principal.user.id,
        filename=file.filename or "drawing",
        content_type=file.content_type,
        data=data,
        customer_id=customer_id,
        quotation_id=quotation_id,
    )
    return jsonable(drawing)


@router.get("/drawings")
def list_drawings(status: str | None = None, paging: tuple[int, int] = Depends(page_args), principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    query = db.query(Drawing).filter(Drawing.organization_id == principal.organization_id)
    if status:
        query = query.filter(Drawing.status == status)
    payload = _page(query.order_by(Drawing.created_at.desc()), *paging)
    payload["items"] = jsonable(payload["items"])
    return payload


@router.get("/drawings/{drawing_id}")
def get_drawing(drawing_id: UUID, principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    drawing = scoped(db, Drawing, principal.organization_id, drawing_id)
    spec = db.query(ExtractedSpecification).filter(ExtractedSpecification.drawing_id == drawing.id).one_or_none()
    evidence = []
    if spec is not None:
        evidence = db.query(ExtractedEvidence).filter(ExtractedEvidence.specification_id == spec.id).all()
    pages = db.query(DrawingPage).filter(DrawingPage.drawing_id == drawing.id).all()
    return jsonable({"drawing": drawing, "specification": spec, "evidence": evidence, "pages": pages})


@router.get("/drawings/{drawing_id}/status")
def drawing_status(drawing_id: UUID, principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    drawing = scoped(db, Drawing, principal.organization_id, drawing_id)
    return jsonable({"id": drawing.id, "status": drawing.status, "error_message": drawing.error_message, "stage_history": drawing.stage_history})


@router.get("/drawings/{drawing_id}/file")
def drawing_file(drawing_id: UUID, principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    drawing = scoped(db, Drawing, principal.organization_id, drawing_id)
    payload = get_storage().read(drawing.storage_key)
    media = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "dxf": "application/dxf"}.get(drawing.detected_format, "application/octet-stream")
    return Response(content=payload, media_type=media)


@router.get("/drawings/{drawing_id}/preview")
def drawing_preview(drawing_id: UUID, principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    drawing = scoped(db, Drawing, principal.organization_id, drawing_id)
    page = db.query(DrawingPage).filter(DrawingPage.drawing_id == drawing.id, DrawingPage.preview_storage_key.is_not(None)).first()
    if page is None or not page.preview_storage_key:
        raise AppError(404, "No preview is available for this drawing.")
    return Response(content=get_storage().read(page.preview_storage_key), media_type="image/png")


@router.post("/analysis/{drawing_id}")
def rerun_analysis(drawing_id: UUID, principal: Principal = Depends(engineer), db: Session = Depends(get_db)):
    drawing = scoped(db, Drawing, principal.organization_id, drawing_id)
    db.commit()
    process_drawing(str(drawing.id))
    db.refresh(drawing)
    return jsonable({"id": drawing.id, "status": drawing.status, "error_message": drawing.error_message})


@router.get("/analysis/{specification_id}")
def get_analysis(specification_id: UUID, principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    spec = scoped(db, ExtractedSpecification, principal.organization_id, specification_id)
    evidence = db.query(ExtractedEvidence).filter(ExtractedEvidence.specification_id == spec.id).all()
    return jsonable({"specification": spec, "evidence": evidence})


@router.patch("/analysis/{specification_id}/verify")
def verify_route(specification_id: UUID, body: VerifyIn, principal: Principal = Depends(engineer), db: Session = Depends(get_db)):
    spec = scoped(db, ExtractedSpecification, principal.organization_id, specification_id)
    if body.confirmed_process and body.confirmed_process not in PROCESSES:
        raise AppError(422, "Process must be milling, turning, drilling, or finishing.")
    if body.units and body.units not in {"mm", "in"}:
        raise AppError(422, "Units must be mm or in.")
    updated = verify_specification(db, spec=spec, actor_id=principal.user.id, payload=body.model_dump())
    return jsonable(updated)


@router.post("/estimation", status_code=201)
def estimate_route(body: EstimateIn, principal: Principal = Depends(engineer), db: Session = Depends(get_db)):
    drawing = scoped(db, Drawing, principal.organization_id, body.drawing_id)
    if drawing.quotation_id:
        quotation = scoped(db, Quotation, principal.organization_id, drawing.quotation_id)
        if quotation.status in {"sent", "accepted"}:
            raise AppError(409, "Sent and accepted quotations cannot be recalculated.")
        estimation = attach_estimation(db, quotation=quotation, drawing=drawing, actor_id=principal.user.id)
    else:
        estimation = create_estimation(db, drawing=drawing, actor_id=principal.user.id)
    return _estimation_payload(db, estimation)


@router.get("/estimation/{estimation_id}")
def get_estimation(estimation_id: UUID, principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    estimation = scoped(db, Estimation, principal.organization_id, estimation_id)
    return _estimation_payload(db, estimation)


@router.post("/estimation/{estimation_id}/recalculate")
def recalculate(estimation_id: UUID, principal: Principal = Depends(engineer), db: Session = Depends(get_db)):
    current = scoped(db, Estimation, principal.organization_id, estimation_id)
    drawing = scoped(db, Drawing, principal.organization_id, current.drawing_id)
    if drawing.quotation_id:
        quotation = scoped(db, Quotation, principal.organization_id, drawing.quotation_id)
        if quotation.status in {"sent", "accepted"}:
            raise AppError(409, "Sent and accepted quotations cannot be recalculated.")
        estimation = attach_estimation(db, quotation=quotation, drawing=drawing, actor_id=principal.user.id)
    else:
        estimation = create_estimation(db, drawing=drawing, actor_id=principal.user.id)
    return _estimation_payload(db, estimation)


@router.post("/quotations", status_code=201)
def create_quote(body: QuotationIn, principal: Principal = Depends(sales), db: Session = Depends(get_db)):
    quotation = create_quotation(
        db,
        organization_id=principal.organization_id,
        actor_id=principal.user.id,
        customer_id=body.customer_id,
        notes=body.notes,
        validity_days=body.validity_days,
    )
    return _quotation_payload(db, quotation)


@router.get("/quotations")
def list_quotes(status: str | None = None, paging: tuple[int, int] = Depends(page_args), principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    query = db.query(Quotation).filter(Quotation.organization_id == principal.organization_id)
    if status:
        query = query.filter(Quotation.status == status)
    payload = _page(query.order_by(Quotation.created_at.desc()), *paging)
    payload["items"] = [_quotation_summary(row) for row in payload["items"]]
    return jsonable(payload)


@router.get("/quotations/{quotation_id}")
def get_quote(quotation_id: UUID, principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    return _quotation_payload(db, scoped(db, Quotation, principal.organization_id, quotation_id))


@router.post("/quotations/{quotation_id}/approve")
def approve_quote(quotation_id: UUID, body: ActionIn, principal: Principal = Depends(reviewer), db: Session = Depends(get_db)):
    return _act(db, principal, quotation_id, "approve", body.comment)


@router.post("/quotations/{quotation_id}/reject")
def reject_quote(quotation_id: UUID, body: ActionIn, principal: Principal = Depends(reviewer), db: Session = Depends(get_db)):
    return _act(db, principal, quotation_id, "reject", body.comment)


@router.post("/quotations/{quotation_id}/send")
def send_quote(quotation_id: UUID, body: ActionIn, principal: Principal = Depends(sales), db: Session = Depends(get_db)):
    return _act(db, principal, quotation_id, "send", body.comment)


@router.post("/quotations/{quotation_id}/accept")
def accept_quote(quotation_id: UUID, body: ActionIn, principal: Principal = Depends(sales), db: Session = Depends(get_db)):
    return _act(db, principal, quotation_id, "accept", body.comment)


@router.get("/quotations/{quotation_id}/pdf")
def quote_pdf(quotation_id: UUID, principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    quotation = scoped(db, Quotation, principal.organization_id, quotation_id)
    payload = render_pdf(db, quotation)
    return Response(content=payload, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{quotation.number}.pdf"'})


@router.get("/quotations/{quotation_id}/history")
def quote_history(quotation_id: UUID, principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    quotation = scoped(db, Quotation, principal.organization_id, quotation_id)
    audits = (
        db.query(AuditLog)
        .filter(AuditLog.organization_id == principal.organization_id, AuditLog.entity_type == "quotation", AuditLog.entity_id == str(quotation.id))
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    approvals = db.query(ApprovalRecord).filter(ApprovalRecord.quotation_id == quotation.id).order_by(ApprovalRecord.created_at.asc()).all()
    return jsonable({"audits": audits, "approvals": approvals})


@router.get("/materials")
def list_materials(principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    materials = db.query(Material).filter(Material.organization_id == principal.organization_id).order_by(Material.name.asc()).all()
    return jsonable([_material_payload(db, material) for material in materials])


@router.post("/materials", status_code=201)
def create_material(body: MaterialIn, principal: Principal = Depends(admin), db: Session = Depends(get_db)):
    material = Material(
        organization_id=principal.organization_id,
        name=body.name.strip(),
        category=body.category.strip(),
        density=body.density,
        availability=body.availability,
        notes=body.notes or SAMPLE_NOTE,
    )
    db.add(material)
    db.flush()
    db.add(
        MaterialPrice(
            organization_id=principal.organization_id,
            material_id=material.id,
            unit_price=body.unit_price,
            currency=body.currency,
            supplier=body.supplier,
            effective_date=date.today(),
            notes=SAMPLE_NOTE,
            created_by=principal.user.id,
        )
    )
    record_audit(db, organization_id=principal.organization_id, actor_id=principal.user.id, entity_type="material", entity_id=str(material.id), action="created", after=body.model_dump())
    db.commit()
    db.refresh(material)
    return _material_payload(db, material)


@router.patch("/materials/{material_id}")
def patch_material(material_id: UUID, body: MaterialPatch, principal: Principal = Depends(admin), db: Session = Depends(get_db)):
    material = scoped(db, Material, principal.organization_id, material_id)
    before = {"density": material.density, "notes": material.notes, "availability": material.availability, "is_active": material.is_active}
    for field in ("density", "availability", "notes", "is_active"):
        value = getattr(body, field)
        if value is not None:
            setattr(material, field, value)
    if body.unit_price is not None:
        db.add(
            MaterialPrice(
                organization_id=principal.organization_id,
                material_id=material.id,
                unit_price=body.unit_price,
                currency=body.currency or "USD",
                supplier=body.supplier,
                effective_date=date.today(),
                notes="Price updated by an organization administrator.",
                created_by=principal.user.id,
            )
        )
    record_audit(
        db,
        organization_id=principal.organization_id,
        actor_id=principal.user.id,
        entity_type="material",
        entity_id=str(material.id),
        action="updated",
        before=jsonable(before),
        after=body.model_dump(exclude_none=True),
    )
    db.commit()
    db.refresh(material)
    return _material_payload(db, material)


@router.get("/settings")
def get_settings_route(principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    settings = db.query(OrganizationCostSettings).filter(OrganizationCostSettings.organization_id == principal.organization_id).one()
    machines = db.query(Machine).filter(Machine.organization_id == principal.organization_id).all()
    processes = db.query(ManufacturingProcess).filter(ManufacturingProcess.organization_id == principal.organization_id).all()
    rates = db.query(MachineRate).filter(MachineRate.organization_id == principal.organization_id).order_by(MachineRate.effective_date.desc()).all()
    return jsonable({"cost_settings": settings, "machines": machines, "processes": processes, "rates": rates})


@router.put("/settings")
def put_settings(body: SettingsIn, principal: Principal = Depends(admin), db: Session = Depends(get_db)):
    settings = db.query(OrganizationCostSettings).filter(OrganizationCostSettings.organization_id == principal.organization_id).one()
    before = {"profit_margin_pct": settings.profit_margin_pct, "overhead_pct": settings.overhead_pct, "stock_fill_ratio": settings.stock_fill_ratio}
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(settings, key, value)
    record_audit(db, organization_id=principal.organization_id, actor_id=principal.user.id, entity_type="cost_settings", entity_id=str(settings.id), action="updated", before=jsonable(before), after=body.model_dump(exclude_none=True))
    db.commit()
    db.refresh(settings)
    return jsonable(settings)


@router.post("/settings/rates", status_code=201)
def add_rate(body: RateIn, principal: Principal = Depends(admin), db: Session = Depends(get_db)):
    process = (
        db.query(ManufacturingProcess)
        .filter(ManufacturingProcess.organization_id == principal.organization_id, ManufacturingProcess.category == body.process_category)
        .one_or_none()
    )
    if process is None:
        raise AppError(404, "Process category not found.")
    rate = MachineRate(
        organization_id=principal.organization_id,
        process_id=process.id,
        hourly_rate=body.hourly_rate,
        setup_hourly_rate=body.setup_hourly_rate,
        currency="USD",
        effective_date=date.today(),
        notes="Updated by an organization administrator.",
    )
    db.add(rate)
    record_audit(db, organization_id=principal.organization_id, actor_id=principal.user.id, entity_type="machine_rate", entity_id=body.process_category, action="rate_added", after=body.model_dump())
    db.commit()
    db.refresh(rate)
    return jsonable(rate)


@router.get("/jobs")
def list_jobs(q: str | None = None, material: str | None = None, process: str | None = None, principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    return jsonable(search_jobs(db, principal.organization_id, q, material, process))


@router.get("/jobs/clusters")
def job_clusters(principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    return jsonable(cluster_jobs(db, principal.organization_id))


@router.get("/jobs/{job_id}/similar")
def job_similar(job_id: UUID, principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    job = scoped(db, ManufacturingJob, principal.organization_id, job_id)
    return jsonable(similar_jobs(db, job))


@router.post("/jobs/{job_id}/actuals")
def job_actuals(job_id: UUID, body: ActualsIn, principal: Principal = Depends(engineer), db: Session = Depends(get_db)):
    job = scoped(db, ManufacturingJob, principal.organization_id, job_id)
    return jsonable(record_actuals(db, job=job, actor_id=principal.user.id, actual_cost=body.actual_cost, actual_hours=body.actual_hours, verified=body.verified))


@router.post("/jobs/{job_id}/training-candidate")
def job_candidate(job_id: UUID, principal: Principal = Depends(admin), db: Session = Depends(get_db)):
    job = scoped(db, ManufacturingJob, principal.organization_id, job_id)
    return jsonable(mark_training_candidate(db, job=job, actor_id=principal.user.id))


@router.get("/ml/models")
def list_models(principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    rows = db.query(ModelVersion).filter(ModelVersion.organization_id == principal.organization_id).order_by(ModelVersion.created_at.desc()).all()
    return jsonable([_model_payload(row) for row in rows])


@router.get("/ml/models/active")
def active_model(principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    row = (
        db.query(ModelVersion)
        .filter(ModelVersion.organization_id == principal.organization_id, ModelVersion.stage == "active")
        .order_by(ModelVersion.approved_at.desc())
        .first()
    )
    if row is None:
        return {"model": None, "health": {"ok": False, "reason": "No active model."}}
    return jsonable({"model": _model_payload(row), "health": artifact_health(Path(row.artifact_path))})


@router.post("/ml/models/import-local")
def import_model(principal: Principal = Depends(admin), db: Session = Depends(get_db)):
    model = import_local_candidate(db, organization_id=principal.organization_id, actor_id=principal.user.id)
    return jsonable(_model_payload(model))


@router.post("/ml/models/{model_id}/promote")
def promote_model(model_id: UUID, body: PromoteIn, principal: Principal = Depends(admin), db: Session = Depends(get_db)):
    model = scoped(db, ModelVersion, principal.organization_id, model_id)
    return jsonable(_model_payload(promote(db, model=model, actor_id=principal.user.id, acknowledge_limitations=body.acknowledge_limitations)))


@router.post("/ml/models/{model_id}/rollback")
def rollback_model(model_id: UUID, principal: Principal = Depends(admin), db: Session = Depends(get_db)):
    model = scoped(db, ModelVersion, principal.organization_id, model_id)
    return jsonable(_model_payload(rollback(db, model=model, actor_id=principal.user.id)))


@router.get("/ml/experiments")
def experiments(principal: Principal = Depends(reader)):
    from app.core.config import get_settings

    directory = Path(get_settings().model_artifact_dir)
    return {"experiments": local_experiments(directory) + mlflow_experiments(), "note": "Local experiment files are the source of truth when MLflow is unreachable."}


@router.get("/ml/metrics")
def metrics_route(principal: Principal = Depends(reader), db: Session = Depends(get_db)):
    active = (
        db.query(ModelVersion)
        .filter(ModelVersion.organization_id == principal.organization_id, ModelVersion.stage == "active")
        .first()
    )
    return {
        "active_model": None if active is None else _model_payload(active),
        "note": "Metrics describe the dataset the model was trained on. Synthetic metrics are not factory accuracy.",
    }


def _act(db: Session, principal: Principal, quotation_id: UUID, action: str, comment: str | None):
    quotation = scoped(db, Quotation, principal.organization_id, quotation_id)
    transition(db, quotation=quotation, actor_id=principal.user.id, action=action, comment=comment)
    db.refresh(quotation)
    return _quotation_payload(db, quotation)


def _estimation_payload(db: Session, estimation: Estimation) -> dict:
    components = db.query(EstimationComponent).filter(EstimationComponent.estimation_id == estimation.id).all()
    return jsonable({"estimation": estimation, "components": components})


def _quotation_summary(quotation: Quotation) -> dict:
    return {
        "id": quotation.id,
        "number": quotation.number,
        "customer_id": quotation.customer_id,
        "status": quotation.status,
        "currency": quotation.currency,
        "total_value": quotation.total_value,
        "validity_until": quotation.validity_until,
        "updated_at": quotation.updated_at,
    }


def _quotation_payload(db: Session, quotation: Quotation) -> dict:
    items = db.query(QuotationItem).filter(QuotationItem.quotation_id == quotation.id).all()
    approvals = db.query(ApprovalRecord).filter(ApprovalRecord.quotation_id == quotation.id).order_by(ApprovalRecord.created_at.asc()).all()
    customer = db.get(Customer, quotation.customer_id)
    return jsonable({"quotation": quotation, "customer": customer, "items": items, "approvals": approvals})


def _material_payload(db: Session, material: Material) -> dict:
    price = (
        db.query(MaterialPrice)
        .filter(MaterialPrice.material_id == material.id)
        .order_by(MaterialPrice.effective_date.desc(), MaterialPrice.created_at.desc())
        .first()
    )
    return jsonable({"material": material, "current_price": price})


def _model_payload(model: ModelVersion) -> dict:
    return {
        "id": model.id,
        "name": model.name,
        "version": model.version,
        "stage": model.stage,
        "algorithm": model.algorithm,
        "metrics": model.metrics,
        "parameters": model.parameters,
        "is_synthetic_training": model.is_synthetic_training,
        "production_ready": model.production_ready,
        "limitations": model.limitations,
        "approved_at": model.approved_at,
        "artifact_path": model.artifact_path,
    }
