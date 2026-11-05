"""Resource booking rules.

Rules enforced when a booking is made:
1. The resource exists in this company and is not out of service.
2. Start is before end, and a booking is at most MAX_BOOKING long.
3. No other ACTIVE booking on the same resource overlaps this time.
4. Two people booking the same resource at the same moment cannot both win:
   every booking also bumps the resource's version (optimistic lock), so the
   second commit fails instead of creating a double booking.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.core.errors import DomainError, is_overlap_violation
from app.models import Client, Role, User
from app.modules.resources.models import Booking, BookingStatus, Resource, ResourceStatus, ResourceType
from app.modules.resources.schemas import BookingIn, ResourceIn, ResourceUpdate

MAX_BOOKING = timedelta(days=90)
MAX_QUERY_RANGE = timedelta(days=62)

_CHANGED_BY_SOMEONE_ELSE = "This resource was just changed by someone else. Reload and try again."


def _commit_or_conflict(db: Session) -> None:
    """Commit; turn an optimistic-lock failure into a friendly 409."""
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        raise DomainError(409, _CHANGED_BY_SOMEONE_ELSE)
    except IntegrityError as exc:
        db.rollback()
        if is_overlap_violation(exc):
            raise DomainError(409, "This resource is already booked at this time")
        raise DomainError(409, "A resource with this name already exists")


# ---------- lookups (automatically limited to the current company) ----------

def get_resource_type(db: Session, type_id: uuid.UUID) -> ResourceType:
    rt = db.get(ResourceType, type_id)
    if rt is None:
        raise DomainError(404, "Resource type not found")
    return rt


def get_resource(db: Session, resource_id: uuid.UUID) -> Resource:
    r = db.get(Resource, resource_id)
    if r is None:
        raise DomainError(404, "Resource not found")
    return r


def get_booking(db: Session, booking_id: uuid.UUID) -> Booking:
    b = db.get(Booking, booking_id)
    if b is None:
        raise DomainError(404, "Booking not found")
    return b


# ---------- types & resources ----------

def delete_resource_type(db: Session, type_id: uuid.UUID) -> None:
    rt = get_resource_type(db, type_id)
    if db.scalar(select(Resource.id).where(Resource.resource_type_id == rt.id).limit(1)):
        raise DomainError(409, "Resource type still has resources")
    db.delete(rt)
    db.commit()


def create_resource(db: Session, body: ResourceIn) -> Resource:
    get_resource_type(db, body.resource_type_id)
    r = Resource(resource_type_id=body.resource_type_id, name=body.name.strip(), location=body.location)
    db.add(r)
    return r  # caller commits (handles duplicate names)


def update_resource(db: Session, resource_id: uuid.UUID, body: ResourceUpdate) -> Resource:
    r = get_resource(db, resource_id)
    # Check 1: the client edited an old copy (e.g. a screen left open for an hour).
    if body.version != r.version:
        raise DomainError(409, _CHANGED_BY_SOMEONE_ELSE)
    if body.name is not None:
        r.name = body.name.strip()
    if body.location is not None:
        r.location = body.location
    if body.status is not None:
        r.status = body.status
    # Check 2: someone else committed between our read and our write (caught at flush).
    _commit_or_conflict(db)
    return r


# ---------- bookings ----------

def _validate_window(start: datetime, end: datetime) -> None:
    if start.tzinfo or end.tzinfo:
        raise DomainError(422, "Use local times without a timezone offset")
    if end <= start:
        raise DomainError(422, "Booking must end after it starts")
    if end - start > MAX_BOOKING:
        raise DomainError(422, f"A booking cannot be longer than {MAX_BOOKING.days} days")


def find_overlap(db: Session, resource_id: uuid.UUID, start: datetime, end: datetime) -> Booking | None:
    stmt = select(Booking).where(
        Booking.resource_id == resource_id,
        Booking.status == BookingStatus.ACTIVE,
        Booking.start_at < end,
        Booking.end_at > start,
    ).limit(1)
    return db.scalar(stmt)


def create_booking(db: Session, body: BookingIn, booked_by: uuid.UUID) -> Booking:
    _validate_window(body.start_at, body.end_at)
    resource = get_resource(db, body.resource_id)
    if resource.status != ResourceStatus.AVAILABLE:
        raise DomainError(409, f"{resource.name} is out of service")

    if body.client_id is not None:
        client = db.get(Client, body.client_id)
        if client is None:
            raise DomainError(404, "Client not found")
        if not client.is_active:
            raise DomainError(422, f"{client.name} is archived")

    clash = find_overlap(db, resource.id, body.start_at, body.end_at)
    if clash is not None:
        raise DomainError(
            409, f"{resource.name} is already booked {clash.start_at:%Y-%m-%d %H:%M} to {clash.end_at:%Y-%m-%d %H:%M}"
        )

    booking = Booking(
        resource_id=resource.id, start_at=body.start_at, end_at=body.end_at, purpose=body.purpose, booked_by=booked_by,
        client_id=body.client_id,
    )
    db.add(booking)
    # Touch the resource so its version is bumped in the same transaction.
    # A concurrent booking that read the same version will now fail at commit.
    resource.updated_at = datetime.now(timezone.utc)
    _commit_or_conflict(db)
    return booking


def cancel_booking(db: Session, booking_id: uuid.UUID, caller: User) -> Booking:
    booking = get_booking(db, booking_id)
    if caller.role == Role.STAFF and booking.booked_by != caller.id:
        raise DomainError(403, "You can only cancel your own bookings")
    if booking.status == BookingStatus.CANCELLED:
        raise DomainError(409, "Booking is already cancelled")
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    return booking


def list_bookings(
    db: Session, start: date, end: date, resource_id: uuid.UUID | None = None, booked_by: uuid.UUID | None = None,
    include_cancelled: bool = False,
) -> list[Booking]:
    if end < start:
        raise DomainError(422, "'to' must be on or after 'from'")
    if end - start > MAX_QUERY_RANGE:
        raise DomainError(422, f"Date range cannot exceed {MAX_QUERY_RANGE.days} days")

    range_start = datetime.combine(start, datetime.min.time())
    range_end = datetime.combine(end + timedelta(days=1), datetime.min.time())
    stmt = select(Booking).where(Booking.start_at < range_end, Booking.end_at > range_start)
    if not include_cancelled:
        stmt = stmt.where(Booking.status == BookingStatus.ACTIVE)
    if resource_id is not None:
        stmt = stmt.where(Booking.resource_id == resource_id)
    if booked_by is not None:
        stmt = stmt.where(Booking.booked_by == booked_by)
    return list(db.scalars(stmt.order_by(Booking.start_at)).unique())


def available_resources(
    db: Session, start: datetime, end: datetime, type_id: uuid.UUID | None = None
) -> list[Resource]:
    """Resources that are in service and free for the whole window, e.g. 'which rooms are free 2-3pm?'"""
    _validate_window(start, end)
    busy = select(Booking.resource_id).where(
        Booking.status == BookingStatus.ACTIVE, Booking.start_at < end, Booking.end_at > start
    )
    stmt = select(Resource).where(Resource.status == ResourceStatus.AVAILABLE, Resource.id.not_in(busy))
    if type_id is not None:
        stmt = stmt.where(Resource.resource_type_id == type_id)
    return list(db.scalars(stmt.order_by(Resource.name)))
