from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import login_throttle
from app.core.security import DUMMY_PASSWORD_HASH, create_access_token, hash_password, verify_password
from app.core.tenancy import set_tenant
from app.db import get_db
from app.models import Role, Tenant, User
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

    tenant = Tenant(name=body.company_name)
    tenant.set_modules(body.modules)
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


def _too_many_attempts(seconds: int) -> HTTPException:
    minutes = max(1, -(-seconds // 60))  # round up
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Too many failed sign-in attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
        headers={"Retry-After": str(seconds)},
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={429: {"description": "Too many failed attempts for this email; see the Retry-After header"}},
)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    # A locked email is refused before the password is even checked, so guessing stops working.
    if seconds := login_throttle.seconds_locked(db, email):
        raise _too_many_attempts(seconds)

    stmt = select(User).where(User.email == email).execution_options(bypass_tenant=True)
    user = db.scalar(stmt)
    # Always run bcrypt, so the response time doesn't reveal whether the email exists.
    password_ok = verify_password(body.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    # Same error for "no such email" and "wrong password", so emails can't be probed.
    if user is None or not user.is_active or not password_ok:
        if seconds := login_throttle.record_failure(db, email):
            raise _too_many_attempts(seconds)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    login_throttle.clear(db, email)
    return TokenResponse(access_token=create_access_token(user.id, user.tenant_id, user.role.value))
