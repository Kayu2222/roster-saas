"""Roster business rules, kept out of the HTTP layer so they are easy to read and test.

Rules enforced when a shift is created:
1. The person exists in this company and is active.
2. Start is before end, and a shift is at most MAX_SHIFT long.
3. If the shift needs a job role, the person must hold that role.
4. The person has no other shift overlapping this time (no double-booking).
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models import User
from app.modules.roster.models import JobRole, Shift, ShiftType, StaffJobRole
from app.modules.roster.schemas import ShiftIn

MAX_SHIFT = timedelta(hours=16)
MAX_QUERY_RANGE = timedelta(days=62)


class RosterError(DomainError):
    """A roster rule was broken. Handled by the shared DomainError handler."""


def _not_found(what: str) -> RosterError:
    return RosterError(404, f"{what} not found")


# ---------- lookups (all automatically limited to the current company) ----------

def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise _not_found("User")
    return user


def get_job_role(db: Session, job_role_id: uuid.UUID) -> JobRole:
    role = db.get(JobRole, job_role_id)
    if role is None:
        raise _not_found("Job role")
    return role


def get_shift_type(db: Session, shift_type_id: uuid.UUID) -> ShiftType:
    st = db.get(ShiftType, shift_type_id)
    if st is None:
        raise _not_found("Shift type")
    return st


def user_job_role_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    rows = db.scalars(select(StaffJobRole.job_role_id).where(StaffJobRole.user_id == user_id))
    return set(rows)


# ---------- qualifications ----------

def set_staff_job_roles(db: Session, user_id: uuid.UUID, job_role_ids: list[uuid.UUID]) -> list[JobRole]:
    get_user(db, user_id)
    roles = [get_job_role(db, rid) for rid in dict.fromkeys(job_role_ids)]  # dedupe, keep order

    for existing in db.scalars(select(StaffJobRole).where(StaffJobRole.user_id == user_id)):
        db.delete(existing)
    db.flush()
    for role in roles:
        db.add(StaffJobRole(user_id=user_id, job_role_id=role.id))
    db.commit()
    return roles


def delete_job_role(db: Session, job_role_id: uuid.UUID) -> None:
    role = get_job_role(db, job_role_id)
    in_use = db.scalar(select(ShiftType.id).where(ShiftType.job_role_id == role.id).limit(1)) or db.scalar(
        select(Shift.id).where(Shift.job_role_id == role.id).limit(1)
    )
    if in_use:
        raise RosterError(409, "Job role is used by shift types or shifts")
    db.delete(role)
    db.commit()


def delete_shift_type(db: Session, shift_type_id: uuid.UUID) -> None:
    st = get_shift_type(db, shift_type_id)
    if db.scalar(select(Shift.id).where(Shift.shift_type_id == st.id).limit(1)):
        raise RosterError(409, "Shift type is used by existing shifts")
    db.delete(st)
    db.commit()


# ---------- shifts ----------

def _resolve_times(db: Session, body: ShiftIn) -> tuple[datetime, datetime, ShiftType | None]:
    if body.shift_type_id is None:
        return body.start_at, body.end_at, None

    st = get_shift_type(db, body.shift_type_id)
    start = datetime.combine(body.date, st.start_time)
    end = datetime.combine(body.date, st.end_time)
    if st.overnight:
        end += timedelta(days=1)
    return start, end, st


def find_clash(db: Session, user_id: uuid.UUID, start: datetime, end: datetime) -> Shift | None:
    """Two time ranges overlap when each one starts before the other ends."""
    stmt = select(Shift).where(Shift.user_id == user_id, Shift.start_at < end, Shift.end_at > start).limit(1)
    return db.scalar(stmt)


def create_shift(db: Session, body: ShiftIn, created_by: uuid.UUID) -> Shift:
    user = get_user(db, body.user_id)
    if not user.is_active:
        raise RosterError(422, "Cannot roster an inactive user")

    start, end, shift_type = _resolve_times(db, body)
    if start.tzinfo or end.tzinfo:
        raise RosterError(422, "Use local times without a timezone offset")
    if end <= start:
        raise RosterError(422, "Shift must end after it starts")
    if end - start > MAX_SHIFT:
        raise RosterError(422, f"Shift cannot be longer than {int(MAX_SHIFT.total_seconds() // 3600)} hours")

    job_role_id = body.job_role_id or (shift_type.job_role_id if shift_type else None)
    if job_role_id is not None:
        role = get_job_role(db, job_role_id)
        if role.id not in user_job_role_ids(db, user.id):
            raise RosterError(409, f"{user.name} is not qualified as {role.name}")

    clash = find_clash(db, user.id, start, end)
    if clash is not None:
        raise RosterError(
            409, f"{user.name} already has a shift {clash.start_at:%Y-%m-%d %H:%M} to {clash.end_at:%Y-%m-%d %H:%M}"
        )

    shift = Shift(
        user_id=user.id,
        start_at=start,
        end_at=end,
        shift_type_id=shift_type.id if shift_type else None,
        job_role_id=job_role_id,
        notes=body.notes,
        created_by=created_by,
    )
    db.add(shift)
    db.commit()
    return shift


def list_shifts(db: Session, start: date, end: date, user_id: uuid.UUID | None = None) -> list[Shift]:
    """Shifts overlapping [start 00:00, end 24:00)."""
    if end < start:
        raise RosterError(422, "'to' must be on or after 'from'")
    if end - start > MAX_QUERY_RANGE:
        raise RosterError(422, f"Date range cannot exceed {MAX_QUERY_RANGE.days} days")

    range_start = datetime.combine(start, datetime.min.time())
    range_end = datetime.combine(end + timedelta(days=1), datetime.min.time())
    stmt = select(Shift).where(Shift.start_at < range_end, Shift.end_at > range_start)
    if user_id is not None:
        stmt = stmt.where(Shift.user_id == user_id)
    return list(db.scalars(stmt.order_by(Shift.start_at)).unique())


def delete_shift(db: Session, shift_id: uuid.UUID) -> None:
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise _not_found("Shift")
    db.delete(shift)
    db.commit()
