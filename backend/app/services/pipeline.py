"""Drawing intake and the asynchronous analysis pipeline."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.serialize import jsonable
from app.db.session import SessionLocal
from app.models import Customer, Drawing, DrawingPage, ExtractedEvidence, ExtractedSpecification, Quotation
from app.services.audit import record_audit
from app.services.extraction import ExtractionResult
from app.services.processors import extract_dxf, extract_image, extract_pdf
from app.services.storage import get_storage

logger = logging.getLogger(__name__)

PDF = b"%PDF"
PNG = b"\x89PNG"
JPEG = b"\xff\xd8\xff"


def detect_format(filename: str, data: bytes) -> str:
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    if suffix == "pdf" and data.startswith(PDF):
        return "pdf"
    if suffix == "png" and data.startswith(PNG):
        return "png"
    if suffix in {"jpg", "jpeg"} and data.startswith(JPEG):
        return "jpg"
    if suffix == "dxf" and not data.startswith(PDF) and not data.startswith(PNG) and not data.startswith(JPEG):
        if data.startswith(b"\x7fELF") or data.startswith(b"MZ"):
            raise AppError(400, "The DXF upload is not a drawing file.")
        return "dxf"
    raise AppError(400, "Upload a PDF, DXF, PNG, or JPEG drawing. The extension and file signature must agree.")


def create_drawing(
    db: Session,
    *,
    organization_id: UUID,
    actor_id: UUID,
    filename: str,
    content_type: str | None,
    data: bytes,
    customer_id: UUID | None,
    quotation_id: UUID | None,
) -> Drawing:
    settings = get_settings()
    if not data:
        raise AppError(400, "The file is empty.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(413, f"File exceeds the {settings.max_upload_mb} MB limit.")
    detected = detect_format(filename, data)
    if customer_id is not None:
        customer = db.get(Customer, customer_id)
        if customer is None or customer.organization_id != organization_id:
            raise AppError(404, "Customer not found.")
    if quotation_id is not None:
        quotation = db.get(Quotation, quotation_id)
        if quotation is None or quotation.organization_id != organization_id:
            raise AppError(404, "Quotation not found.")
        if customer_id is None:
            customer_id = quotation.customer_id
    storage = get_storage()
    key = storage.save(str(organization_id), Path(filename).name, data)
    now = datetime.now(timezone.utc).isoformat()
    drawing = Drawing(
        organization_id=organization_id,
        customer_id=customer_id,
        quotation_id=quotation_id,
        uploaded_by=actor_id,
        original_filename=Path(filename).name,
        content_type=content_type,
        detected_format=detected,
        storage_key=key,
        byte_size=len(data),
        status="received",
        stage_history=[{"stage": "received", "at": now, "note": "Document received."}],
    )
    db.add(drawing)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        entity_type="drawing",
        entity_id=str(drawing.id),
        action="uploaded",
        after={"filename": Path(filename).name, "format": detected, "bytes": len(data)},
    )
    db.commit()
    db.refresh(drawing)
    schedule_processing(drawing.id)
    db.refresh(drawing)
    return drawing


def schedule_processing(drawing_id: UUID) -> None:
    settings = get_settings()
    if settings.process_sync:
        process_drawing(str(drawing_id))
        return
    if settings.process_inline:
        threading.Thread(target=process_drawing, args=(str(drawing_id),), daemon=True).start()
        return
    from app.workers.celery_app import process_drawing_task

    process_drawing_task.delay(str(drawing_id))


def process_drawing(drawing_id: str) -> None:
    db = SessionLocal()
    try:
        drawing = db.get(Drawing, UUID(drawing_id))
        if drawing is None:
            return
        drawing.processing_started_at = datetime.now(timezone.utc)
        _stage(db, drawing, "validating", "File signature was checked at upload.")
        storage = get_storage()
        path = storage.absolute(drawing.storage_key)
        if path is None:
            local = Path(get_settings().storage_dir) / drawing.storage_key
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(storage.read(drawing.storage_key))
            path = local
        _stage(db, drawing, "preprocessing", f"{drawing.detected_format.upper()} preprocessing started.")
        if drawing.detected_format == "pdf":
            _stage(db, drawing, "ocr", "Checking embedded text before OCR.")
            result = extract_pdf(path)
        elif drawing.detected_format == "dxf":
            _stage(db, drawing, "ocr", "OCR does not apply to DXF. Text entities will be read directly.")
            _stage(db, drawing, "geometry", "Reading DXF entities.")
            result = extract_dxf(path)
        else:
            _stage(db, drawing, "ocr", "Running image preprocessing and OCR.")
            result = extract_image(path)
        _stage(db, drawing, "geometry", "Geometric candidates recorded.")
        _stage(db, drawing, "features", "Drawing features recorded as candidates, not as a process decision.")
        _stage(db, drawing, "specifications", "Structured specification saved with evidence.")
        _replace_specification(db, drawing, result)
        _stage(db, drawing, "confidence", "Automatic confidence is capped below human verification.")
        drawing.status = "awaiting_verification"
        drawing.processing_completed_at = datetime.now(timezone.utc)
        drawing.error_message = None
        history = list(drawing.stage_history or [])
        history.append(
            {
                "stage": "awaiting_verification",
                "at": datetime.now(timezone.utc).isoformat(),
                "note": "Human verification is required before estimation.",
            }
        )
        drawing.stage_history = history
        db.commit()
    except Exception as exc:
        logger.exception("Drawing processing failed")
        db.rollback()
        drawing = db.get(Drawing, UUID(drawing_id))
        if drawing is not None:
            drawing.status = "failed"
            drawing.error_message = str(exc)
            history = list(drawing.stage_history or [])
            history.append({"stage": "failed", "at": datetime.now(timezone.utc).isoformat(), "note": str(exc)})
            drawing.stage_history = history
            db.commit()
    finally:
        db.close()


def _stage(db: Session, drawing: Drawing, stage: str, note: str) -> None:
    drawing.status = stage
    history = list(drawing.stage_history or [])
    history.append({"stage": stage, "at": datetime.now(timezone.utc).isoformat(), "note": note})
    drawing.stage_history = history
    db.commit()


def _replace_specification(db: Session, drawing: Drawing, result: ExtractionResult) -> None:
    existing = db.query(ExtractedSpecification).filter(ExtractedSpecification.drawing_id == drawing.id).one_or_none()
    if existing is not None:
        db.query(ExtractedEvidence).filter(ExtractedEvidence.specification_id == existing.id).delete()
        db.delete(existing)
        db.flush()
    db.query(DrawingPage).filter(DrawingPage.drawing_id == drawing.id).delete()
    preview_key = None
    if result.preview_png:
        preview_key = get_storage().save(str(drawing.organization_id), "preview.png", result.preview_png)
    for page in result.pages:
        db.add(
            DrawingPage(
                drawing_id=drawing.id,
                page_number=page["page_number"],
                width=page.get("width"),
                height=page.get("height"),
                text_excerpt=page.get("text_excerpt"),
                preview_storage_key=preview_key if page["page_number"] == 1 else None,
            )
        )
    spec = ExtractedSpecification(
        organization_id=drawing.organization_id,
        drawing_id=drawing.id,
        part_name=result.part_name,
        drawing_number=result.drawing_number,
        material=result.material,
        units=result.units,
        length=_dec(result.length),
        width=_dec(result.width),
        height=_dec(result.height),
        diameter=_dec(result.diameter),
        thickness=_dec(result.thickness),
        tolerances=result.tolerances,
        surface_finish=result.surface_finish,
        quantity=result.quantity,
        manufacturing_notes=result.manufacturing_notes,
        detected_features=jsonable(result.detected_features),
        missing_information=result.missing_information,
        confidence_scores=result.confidence_scores,
        verification_status="unverified",
    )
    db.add(spec)
    db.flush()
    for item in result.evidence:
        db.add(
            ExtractedEvidence(
                organization_id=drawing.organization_id,
                specification_id=spec.id,
                drawing_id=drawing.id,
                field_name=item.field_name,
                value_text=item.value,
                source_document=item.source_document or drawing.original_filename,
                location=item.location,
                method=item.method,
                confidence=item.confidence,
                verification_status="unverified",
            )
        )


def _dec(value):
    if value is None:
        return None
    return Decimal(str(value))
