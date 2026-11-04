import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db import get_db
from app.deps import get_current_user, require_module, require_roles
from app.models import Module, Role, User
from app.modules.resources import service
from app.modules.resources.models import Resource, ResourceType
from app.modules.resources.schemas import (
    BookingIn,
    BookingOut,
    ResourceIn,
    ResourceOut,
    ResourceTypeIn,
    ResourceTypeOut,
    ResourceUpdate,
)

router = APIRouter(
    prefix="/api/resources", tags=["Resources"], dependencies=[Depends(require_module(Module.RESOURCE))]
)

manager_only = require_roles(Role.OWNER, Role.MANAGER)


def _commit_unique(db: Session, what: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DomainError(409, f"A {what} with this name already exists")


# Static paths are declared before "/{resource_id}" so they are matched first.

# ---------- resource types ----------

@router.get("/types", response_model=list[ResourceTypeOut])
def list_types(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(ResourceType).order_by(ResourceType.name)).all()


@router.post("/types", response_model=ResourceTypeOut, status_code=status.HTTP_201_CREATED)
def create_type(body: ResourceTypeIn, _: User = Depends(manager_only), db: Session = Depends(get_db)):
    rt = ResourceType(name=body.name.strip())
    db.add(rt)
    _commit_unique(db, "resource type")
    return rt


@router.delete("/types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_type(type_id: uuid.UUID, _: User = Depends(manager_only), db: Session = Depends(get_db)):
    service.delete_resource_type(db, type_id)


# ---------- availability ----------

@router.get("/availability", response_model=list[ResourceOut])
def availability(
    start_at: datetime = Query(examples=["2026-11-10T14:00"]),
    end_at: datetime = Query(examples=["2026-11-10T15:00"]),
    type_id: uuid.UUID | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Which resources are free for the whole window? Optionally only one type."""
    return service.available_resources(db, start_at, end_at, type_id)


# ---------- bookings ----------

@router.post("/bookings", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(body: BookingIn, caller: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Anyone in the company can book. Rejects overlaps, out-of-service resources and invalid times."""
    return service.create_booking(db, body, booked_by=caller.id)


@router.get("/bookings", response_model=list[BookingOut])
def list_bookings(
    date_from: date = Query(alias="from", examples=["2026-11-09"]),
    date_to: date = Query(alias="to", examples=["2026-11-15"]),
    resource_id: uuid.UUID | None = None,
    include_cancelled: bool = False,
    caller: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Managers see all bookings. Staff see only their own (use /availability to find free resources)."""
    booked_by = caller.id if caller.role == Role.STAFF else None
    return service.list_bookings(db, date_from, date_to, resource_id, booked_by, include_cancelled)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: uuid.UUID, caller: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Staff can cancel their own bookings; managers can cancel any. Cancelled bookings are kept for history."""
    return service.cancel_booking(db, booking_id, caller)


# ---------- resources ----------

@router.get("", response_model=list[ResourceOut])
def list_resources(
    type_id: uuid.UUID | None = None, _: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    stmt = select(Resource).order_by(Resource.name)
    if type_id is not None:
        stmt = stmt.where(Resource.resource_type_id == type_id)
    return db.scalars(stmt).all()


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
def create_resource(body: ResourceIn, _: User = Depends(manager_only), db: Session = Depends(get_db)):
    r = service.create_resource(db, body)
    _commit_unique(db, "resource")
    return r


@router.get("/{resource_id}", response_model=ResourceOut)
def get_resource(resource_id: uuid.UUID, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.get_resource(db, resource_id)


@router.patch("/{resource_id}", response_model=ResourceOut)
def update_resource(
    resource_id: uuid.UUID, body: ResourceUpdate, _: User = Depends(manager_only), db: Session = Depends(get_db)
):
    """Rename, move or take a resource out of service. Requires the current `version` (optimistic locking)."""
    return service.update_resource(db, resource_id, body)
