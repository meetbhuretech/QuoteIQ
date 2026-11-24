"""Request-scoped authentication and role checks.

The organization id for a normal user always comes from the token membership.
A caller cannot point a body field at another tenant and read it.
"""

from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Organization, OrganizationMember, User

bearer = HTTPBearer(auto_error=False)


class Principal:
    def __init__(self, user: User, organization: Organization | None, role: str | None):
        self.user = user
        self.organization = organization
        self.role = role

    @property
    def organization_id(self) -> UUID:
        if self.organization is None:
            raise AppError(400, "Select an organization with the X-Organization-Id header.")
        return self.organization.id


def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if credentials is None:
        raise AppError(401, "Authentication is required.")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = UUID(payload["sub"])
    except Exception as exc:
        raise AppError(401, "The session token is invalid or expired.") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "This user is not active.")
    if user.is_super_admin:
        raw_org = request.headers.get("X-Organization-Id") or payload.get("org_id")
    else:
        raw_org = payload.get("org_id")
    organization = db.get(Organization, UUID(raw_org)) if raw_org else None
    membership = None
    if organization is not None:
        membership = (
            db.query(OrganizationMember)
            .filter(OrganizationMember.user_id == user.id, OrganizationMember.organization_id == organization.id)
            .one_or_none()
        )
    if not user.is_super_admin:
        if organization is None or membership is None:
            raise AppError(403, "You do not have access to this organization.")
        role = membership.role
    else:
        role = membership.role if membership else "org_admin"
    return Principal(user, organization, role)


def require_roles(*roles: str):
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.organization is None:
            raise AppError(400, "Select an organization with the X-Organization-Id header.")
        if principal.user.is_super_admin or principal.role == "org_admin" or principal.role in roles:
            return principal
        raise AppError(403, "You do not have access to this action.")
        return principal

    return dependency


def scoped(db: Session, model, organization_id: UUID, row_id: UUID):
    row = db.get(model, row_id)
    if row is None or getattr(row, "organization_id", None) != organization_id:
        raise AppError(404, "Not found.")
    return row
