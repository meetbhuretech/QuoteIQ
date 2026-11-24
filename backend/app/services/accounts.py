"""Registration, login, and organization membership."""

import re
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Organization, OrganizationMember, User
from app.services.audit import record_audit
from app.services.org_seed import seed_organization


def validate_password(password: str) -> None:
    if len(password) < 10 or re.search(r"[A-Za-z]", password) is None or re.search(r"\d", password) is None:
        raise AppError(422, "Password must be at least 10 characters and include a letter and a number.", "weak_password")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (slug or "organization")[:180]


def register(db: Session, *, email: str, password: str, full_name: str, organization_name: str) -> dict:
    validate_password(password)
    normalized = email.strip().lower()
    if db.query(User).filter(User.email == normalized).first():
        raise AppError(409, "An account with this email already exists.", "email_taken")
    user = User(email=normalized, full_name=full_name.strip(), hashed_password=hash_password(password), is_active=True)
    db.add(user)
    db.flush()
    slug = slugify(organization_name)
    if db.query(Organization).filter(Organization.slug == slug).first():
        slug = f"{slug}-{uuid4().hex[:6]}"
    organization = Organization(name=organization_name.strip(), slug=slug)
    db.add(organization)
    db.flush()
    db.add(OrganizationMember(organization_id=organization.id, user_id=user.id, role="org_admin"))
    seed_organization(db, organization.id, user.id)
    record_audit(
        db,
        organization_id=organization.id,
        actor_id=user.id,
        entity_type="organization",
        entity_id=str(organization.id),
        action="created",
        after={"name": organization.name},
    )
    db.commit()
    return _session(user, organization, "org_admin")


def login(db: Session, *, email: str, password: str) -> dict:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        raise AppError(401, "Email or password is incorrect.", "invalid_credentials")
    membership = (
        db.query(OrganizationMember).filter(OrganizationMember.user_id == user.id).order_by(OrganizationMember.created_at.asc()).first()
    )
    organization = db.get(Organization, membership.organization_id) if membership else None
    role = membership.role if membership else None
    if organization is None and not user.is_super_admin:
        raise AppError(403, "This user is not a member of an organization.", "no_organization")
    return _session(user, organization, role)


def switch_organization(db: Session, *, user: User, organization_id: UUID) -> dict:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise AppError(404, "Organization not found.")
    membership = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.user_id == user.id, OrganizationMember.organization_id == organization_id)
        .first()
    )
    if membership is None and not user.is_super_admin:
        raise AppError(403, "You are not a member of that organization.")
    return _session(user, organization, membership.role if membership else "org_admin")


def add_member(db: Session, *, organization_id: UUID, actor_id: UUID, email: str, full_name: str, password: str, role: str) -> OrganizationMember:
    from app.domain.constants import ROLES

    if role not in ROLES:
        raise AppError(422, "Unknown role.")
    validate_password(password)
    normalized = email.strip().lower()
    user = db.query(User).filter(User.email == normalized).first()
    if user is None:
        user = User(email=normalized, full_name=full_name.strip(), hashed_password=hash_password(password), is_active=True)
        db.add(user)
        db.flush()
    existing = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == organization_id, OrganizationMember.user_id == user.id)
        .first()
    )
    if existing:
        raise AppError(409, "That person is already a member of this organization.")
    member = OrganizationMember(organization_id=organization_id, user_id=user.id, role=role)
    db.add(member)
    record_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        entity_type="organization_member",
        entity_id=str(user.id),
        action="member_added",
        after={"email": normalized, "role": role},
    )
    db.commit()
    db.refresh(member)
    return member


def _session(user: User, organization: Organization | None, role: str | None) -> dict:
    token = create_access_token(
        user_id=user.id,
        organization_id=organization.id if organization else None,
        role=role,
        is_super_admin=user.is_super_admin,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "is_super_admin": user.is_super_admin},
        "organization": None if organization is None else {"id": organization.id, "name": organization.name, "slug": organization.slug},
        "role": role,
    }
