from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.core.tenancy import set_tenant
from app.db import get_db
from app.models import Module, Role, Tenant, User
from app.schemas import LoginRequest, RegisterCompanyRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _email_taken(db: Session, email: str) -> bool:
    # Login/sign-up happen before we know the tenant, so this is a deliberate,
    # explicit bypass of tenant filtering (see app/core/tenancy.py).
    stmt = select(User.id).where(User.email == email).execution_options(bypass_tenant=True)
    return db.scalar(stmt) is not None


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_company(body: RegisterCompanyRequest, db: Session = Depends(get_db)):
    """Sign up: creates a new company, its owner account, and switches on the chosen modules."""
    email = body.email.lower()
    if _email_taken(db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    tenant = Tenant(
        name=body.company_name,
        roster_enabled=Module.ROSTER in body.modules,
        resource_enabled=Module.RESOURCE in body.modules,
    )
    db.add(tenant)
    db.flush()  # assigns tenant.id

    set_tenant(db, tenant.id)
    owner = User(email=email, name=body.owner_name, password_hash=hash_password(body.password), role=Role.OWNER)
    db.add(owner)
    try:
        db.commit()
    except IntegrityError:  # two sign-ups with the same email at the same moment
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    return TokenResponse(access_token=create_access_token(owner.id, tenant.id, owner.role.value))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    stmt = select(User).where(User.email == body.email.lower()).execution_options(bypass_tenant=True)
    user = db.scalar(stmt)
    # Same error for "no such email" and "wrong password", so emails can't be probed.
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return TokenResponse(access_token=create_access_token(user.id, user.tenant_id, user.role.value))
