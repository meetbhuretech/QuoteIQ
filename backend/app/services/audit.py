"""Audit trail for human corrections and approvals."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.serialize import jsonable
from app.models import AuditLog


def record_audit(
    db: Session,
    *,
    organization_id: UUID,
    actor_id: UUID | None,
    entity_type: str,
    entity_id: str,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            before=jsonable(before) if before is not None else None,
            after=jsonable(after) if after is not None else None,
        )
    )
