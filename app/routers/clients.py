"""Clients: the people a company serves (patients, customers, students, guests). They don't sign in.

Anyone in the company can add or update a client (reception registers walk-ins);
only owners and managers can archive one. Archived clients keep their history.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_tenant, get_current_user
from app.models import Client, Module, Role, Tenant, User

router = APIRouter(prefix="/api/clients", tags=["Clients"])

NOTES_HINT = "Short practical notes only. Don't store medical or other sensitive details here."


class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=1000, description=NOTES_HINT)


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=1000, description=NOTES_HINT)
    is_active: bool | None = Field(default=None, description="false archives the client (owners and managers only)")


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    notes: str | None
    is_active: bool
    created_at: datetime


class ActivityItem(BaseModel):
    kind: str  # "booking" or "usage"
    at: datetime
    title: str
    detail: str | None = None


def get_client(db: Session, client_id: uuid.UUID) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return client


@router.get("", response_model=list[ClientOut])
def list_clients(
    q: str | None = Query(default=None, max_length=120, description="Search name, email or phone"),
    include_archived: bool = False,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Client)
    if not include_archived:
        stmt = stmt.where(Client.is_active.is_(True))
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Client.name).like(like), func.lower(Client.email).like(like), Client.phone.like(like)))
    return db.scalars(stmt.order_by(Client.name).limit(200)).all()


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(body: ClientIn, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    client = Client(**body.model_dump())
    client.name = client.name.strip()
    db.add(client)
    db.commit()
    return client


@router.get("/{client_id}", response_model=ClientOut)
def read_client(client_id: uuid.UUID, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_client(db, client_id)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: uuid.UUID, body: ClientUpdate, caller: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    client = get_client(db, client_id)
    changes = body.model_dump(exclude_unset=True)
    if "is_active" in changes and caller.role == Role.STAFF:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners and managers can archive clients")
    for field, value in changes.items():
        setattr(client, field, value.strip() if field == "name" and value else value)
    db.commit()
    return client


@router.get("/{client_id}/activity", response_model=list[ActivityItem])
def client_activity(
    client_id: uuid.UUID,
    _: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Everything linked to this client, newest first: bookings (assets) and items used (products)."""
    get_client(db, client_id)
    items: list[ActivityItem] = []

    if tenant.has_module(Module.RESOURCE):
        from app.modules.resources.models import Booking, BookingStatus

        for b in db.scalars(select(Booking).where(Booking.client_id == client_id)).unique():
            when = f"{b.start_at:%d %b %H:%M} to {b.end_at:%d %b %H:%M}"
            cancelled = " (cancelled)" if b.status == BookingStatus.CANCELLED else ""
            items.append(ActivityItem(kind="booking", at=b.start_at, title=f"{b.resource.name}{cancelled}", detail=when))

    if tenant.has_module(Module.INVENTORY):
        from app.modules.inventory.models import MovementReason, StockMovement

        stmt = select(StockMovement).where(StockMovement.client_id == client_id, StockMovement.reason == MovementReason.USED)
        for m in db.scalars(stmt).unique():
            items.append(ActivityItem(kind="usage", at=m.created_at.replace(tzinfo=None), title=m.product.name,
                                      detail=f"{-m.change} {m.product.unit}" + (f", {m.note}" if m.note else "")))

    return sorted(items, key=lambda i: i.at, reverse=True)
