"""Persistence models.

Tenant-owned tables include organization_id. Services must filter on it.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


def json_type():
    return JSON().with_variant(JSONB(), "postgresql")


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False, index=True)


class OrganizationMember(Base, TimestampMixin):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_members_org_user"),
        Index("ix_organization_members_organization_id", "organization_id"),
        Index("ix_organization_members_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (Index("ix_customers_organization_id", "organization_id"),)

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Quotation(Base, TimestampMixin):
    __tablename__ = "quotations"
    __table_args__ = (
        UniqueConstraint("organization_id", "number", name="uq_quotations_org_number"),
        Index("ix_quotations_organization_id", "organization_id"),
        Index("ix_quotations_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    number: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    total_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    validity_until: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    assumptions: Mapped[list] = mapped_column(json_type(), default=list)
    missing_information: Mapped[list] = mapped_column(json_type(), default=list)
    confidence_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    confidence_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))


class Drawing(Base, TimestampMixin):
    __tablename__ = "drawings"
    __table_args__ = (
        Index("ix_drawings_organization_id", "organization_id"),
        Index("ix_drawings_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    quotation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("quotations.id"))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(200))
    detected_format: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="received", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    stage_history: Mapped[list] = mapped_column(json_type(), default=list)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DrawingPage(Base):
    __tablename__ = "drawing_pages"
    __table_args__ = (Index("ix_drawing_pages_drawing_id", "drawing_id"),)

    id: Mapped[uuid.UUID] = pk()
    drawing_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("drawings.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    height: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    text_excerpt: Mapped[str | None] = mapped_column(Text)
    preview_storage_key: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExtractedSpecification(Base, TimestampMixin):
    __tablename__ = "extracted_specifications"
    __table_args__ = (
        UniqueConstraint("drawing_id", name="uq_extracted_specifications_drawing"),
        Index("ix_extracted_specifications_organization_id", "organization_id"),
    )

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    drawing_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("drawings.id"), nullable=False)
    part_name: Mapped[str | None] = mapped_column(String(200))
    drawing_number: Mapped[str | None] = mapped_column(String(120))
    material: Mapped[str | None] = mapped_column(String(200))
    material_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("materials.id"))
    units: Mapped[str | None] = mapped_column(String(10))
    length: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    width: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    height: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    diameter: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    thickness: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    tolerances: Mapped[list] = mapped_column(json_type(), default=list)
    surface_finish: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[int | None] = mapped_column(Integer)
    manufacturing_notes: Mapped[list] = mapped_column(json_type(), default=list)
    detected_features: Mapped[list] = mapped_column(json_type(), default=list)
    missing_information: Mapped[list] = mapped_column(json_type(), default=list)
    confidence_scores: Mapped[dict] = mapped_column(json_type(), default=dict)
    confirmed_process: Mapped[str | None] = mapped_column(String(40))
    confirmed_machine_category: Mapped[str | None] = mapped_column(String(40))
    confirmed_machine_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    confirmed_setup_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    confirmed_hole_count: Mapped[int | None] = mapped_column(Integer)
    confirmed_feature_count: Mapped[int | None] = mapped_column(Integer)
    confirmed_volume_cm3: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    confirmed_setup_complexity: Mapped[int | None] = mapped_column(Integer)
    confirmed_finishing_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    finishing_required: Mapped[bool | None] = mapped_column(Boolean)
    verification_status: Mapped[str] = mapped_column(String(40), default="unverified", nullable=False)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtractedEvidence(Base):
    __tablename__ = "extracted_evidence"
    __table_args__ = (Index("ix_extracted_evidence_specification_id", "specification_id"),)

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    specification_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("extracted_specifications.id"), nullable=False)
    drawing_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("drawings.id"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(80), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text)
    source_document: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[str | None] = mapped_column(String(300))
    method: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(40), default="unverified", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Material(Base, TimestampMixin):
    __tablename__ = "materials"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_materials_org_name"),
        Index("ix_materials_organization_id", "organization_id"),
    )

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    density: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    availability: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MaterialPrice(Base):
    __tablename__ = "material_prices"
    __table_args__ = (Index("ix_material_prices_material_id", "material_id"),)

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("materials.id"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    supplier: Mapped[str | None] = mapped_column(String(200))
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Machine(Base, TimestampMixin):
    __tablename__ = "machines"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_machines_org_name"),
        Index("ix_machines_organization_id", "organization_id"),
    )

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ManufacturingProcess(Base, TimestampMixin):
    __tablename__ = "manufacturing_processes"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_processes_org_name"),
        Index("ix_manufacturing_processes_organization_id", "organization_id"),
    )

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class MachineRate(Base):
    __tablename__ = "machine_rates"
    __table_args__ = (Index("ix_machine_rates_organization_id", "organization_id"),)

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    machine_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("machines.id"))
    process_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("manufacturing_processes.id"))
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    setup_hourly_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OrganizationCostSettings(Base, TimestampMixin):
    __tablename__ = "organization_cost_settings"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_cost_settings_org"),)

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    scrap_allowance_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=5, nullable=False)
    tooling_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    labor_hourly_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    overhead_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=15, nullable=False)
    packaging_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    profit_margin_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=12, nullable=False)
    default_setup_hours: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=1, nullable=False)
    hours_per_day: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=8, nullable=False)
    shipping_days: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    stock_fill_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=1, nullable=False)
    default_validity_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)


class Estimation(Base, TimestampMixin):
    __tablename__ = "estimations"
    __table_args__ = (Index("ix_estimations_organization_id", "organization_id"),)

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    drawing_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("drawings.id"), nullable=False)
    specification_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("extracted_specifications.id"), nullable=False)
    quotation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("quotations.id"))
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("model_versions.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    deterministic_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    deterministic_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ml_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    ml_is_prediction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text)
    production_hours_deterministic: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    production_hours_ml: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    lead_time_days_deterministic: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    lead_time_days_ml: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    confidence_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    confidence_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    assumptions: Mapped[list] = mapped_column(json_type(), default=list)
    missing_information: Mapped[list] = mapped_column(json_type(), default=list)
    explanation: Mapped[dict] = mapped_column(json_type(), default=dict)
    disclaimer: Mapped[str] = mapped_column(Text, default="", nullable=False)


class EstimationComponent(Base):
    __tablename__ = "estimation_components"
    __table_args__ = (Index("ix_estimation_components_estimation_id", "estimation_id"),)

    id: Mapped[uuid.UUID] = pk()
    estimation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("estimations.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    inputs: Mapped[dict] = mapped_column(json_type(), default=dict)
    complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class QuotationItem(Base, TimestampMixin):
    __tablename__ = "quotation_items"
    __table_args__ = (Index("ix_quotation_items_quotation_id", "quotation_id"),)

    id: Mapped[uuid.UUID] = pk()
    quotation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("quotations.id"), nullable=False)
    drawing_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("drawings.id"), nullable=False)
    estimation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("estimations.id"), nullable=False)
    part_name: Mapped[str | None] = mapped_column(String(200))
    drawing_reference: Mapped[str | None] = mapped_column(String(120))
    material: Mapped[str | None] = mapped_column(String(200))
    processes: Mapped[list] = mapped_column(json_type(), default=list)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    material_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    machining_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    setup_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    finishing_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    additional_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    profit_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    total: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    production_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    lead_time_days: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    assumptions: Mapped[list] = mapped_column(json_type(), default=list)
    missing_information: Mapped[list] = mapped_column(json_type(), default=list)
    confidence_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    confidence_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    ml_total_advisory: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))


class ManufacturingJob(Base, TimestampMixin):
    __tablename__ = "manufacturing_jobs"
    __table_args__ = (Index("ix_manufacturing_jobs_organization_id", "organization_id"),)

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    quotation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("quotations.id"))
    drawing_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("drawings.id"))
    part_name: Mapped[str | None] = mapped_column(String(200))
    drawing_number: Mapped[str | None] = mapped_column(String(120))
    material_name: Mapped[str | None] = mapped_column(String(200))
    material_category: Mapped[str | None] = mapped_column(String(80))
    process: Mapped[str | None] = mapped_column(String(40))
    quantity: Mapped[int | None] = mapped_column(Integer)
    feature_vector: Mapped[dict] = mapped_column(json_type(), default=dict)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    estimated_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    actual_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    training_candidate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    data_origin: Mapped[str] = mapped_column(String(40), default="operations", nullable=False)


class TrainingDataset(Base):
    __tablename__ = "training_datasets"
    __table_args__ = (Index("ix_training_datasets_organization_id", "organization_id"),)

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    origin: Mapped[str] = mapped_column(String(40), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict] = mapped_column("metadata", json_type(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"
    __table_args__ = (Index("ix_model_versions_organization_id", "organization_id", "stage"),)

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("training_datasets.id"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    target: Mapped[str] = mapped_column(String(80), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(80), nullable=False)
    stage: Mapped[str] = mapped_column(String(40), default="candidate", nullable=False)
    metrics: Mapped[dict] = mapped_column(json_type(), default=dict)
    parameters: Mapped[dict] = mapped_column(json_type(), default=dict)
    artifact_path: Mapped[str] = mapped_column(String(500), nullable=False)
    is_synthetic_training: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    production_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    limitations: Mapped[str] = mapped_column(Text, default="", nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PredictionLog(Base):
    __tablename__ = "prediction_logs"
    __table_args__ = (Index("ix_prediction_logs_organization_id", "organization_id"),)

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("model_versions.id"))
    estimation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("estimations.id"))
    latency_ms: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    output: Mapped[dict] = mapped_column(json_type(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ApprovalRecord(Base):
    __tablename__ = "approval_records"
    __table_args__ = (Index("ix_approval_records_quotation_id", "quotation_id"),)

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    quotation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("quotations.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_organization_id", "organization_id"),
        Index("ix_audit_logs_entity", "organization_id", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    before: Mapped[dict | None] = mapped_column(json_type())
    after: Mapped[dict | None] = mapped_column(json_type())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# Imported for metadata registration side effects in Alembic.
_ = text
