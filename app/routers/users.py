import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db import get_db
from app.deps import get_current_user, require_roles
from app.models import Role, User
from app.schemas import CreateUserRequest, UserOut

router = APIRouter(prefix="/api/users", tags=["Users"])

# Note: no query below filters by tenant_id. Isolation is automatic (app/core/tenancy.py).


@router.get("", response_model=list[UserOut])
def list_users(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.created_at)).all()


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:  # also the answer when the user exists in ANOTHER company
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    caller: User = Depends(require_roles(Role.OWNER, Role.MANAGER)),
    db: Session = Depends(get_db),
):
    """Owner or manager adds a person to their company."""
    if body.role == Role.OWNER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A company has exactly one owner")
    if body.role == Role.MANAGER and caller.role != Role.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can add managers")

    user = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    return user
