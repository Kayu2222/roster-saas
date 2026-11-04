import uuid
from datetime import date

from fastapi import APIRouter, Body, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_module, require_roles
from app.models import Module, Role, User
from app.modules.roster import service
from app.modules.roster.models import JobRole, ShiftType
from app.modules.roster.schemas import (
    JobRoleIn,
    JobRoleOut,
    ShiftIn,
    ShiftOut,
    ShiftTypeIn,
    ShiftTypeOut,
    StaffJobRolesIn,
)
from app.modules.roster.service import RosterError

router = APIRouter(prefix="/api/roster", tags=["Roster"], dependencies=[Depends(require_module(Module.ROSTER))])

manager_only = require_roles(Role.OWNER, Role.MANAGER)

# Clean request examples for Swagger (pick one from the "Examples" dropdown).
SHIFT_TYPE_EXAMPLES = {
    "any_staff": {
        "summary": "Day shift, anyone can work it",
        "value": {"name": "Morning", "start_time": "07:00", "end_time": "15:00"},
    },
    "role_required": {
        "summary": "Only staff holding a job role",
        "value": {"name": "Ward AM", "start_time": "07:00", "end_time": "15:00",
                  "job_role_id": "PASTE-JOB-ROLE-ID"},
    },
    "overnight": {
        "summary": "Overnight shift (ends next day)",
        "value": {"name": "Night", "start_time": "22:00", "end_time": "06:00"},
    },
}

SHIFT_EXAMPLES = {
    "from_shift_type": {
        "summary": "Use a shift type + date (most common)",
        "description": "Times come from the shift type. The job role, if any, comes from the shift type too.",
        "value": {"user_id": "PASTE-USER-ID", "shift_type_id": "PASTE-SHIFT-TYPE-ID", "date": "2026-11-10"},
    },
    "custom_times": {
        "summary": "Custom times (one-off cover shift)",
        "description": "No shift type. Give exact local start and end times, without a timezone.",
        "value": {"user_id": "PASTE-USER-ID", "start_at": "2026-11-10T10:00", "end_at": "2026-11-10T14:00",
                  "notes": "Covering for Ben"},
    },
}


async def roster_error_handler(_: Request, exc: RosterError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def _conflict_if_duplicate(db: Session, what: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise RosterError(409, f"A {what} with this name already exists")


# ---------- job roles ----------

@router.get("/job-roles", response_model=list[JobRoleOut])
def list_job_roles(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(JobRole).order_by(JobRole.name)).all()


@router.post("/job-roles", response_model=JobRoleOut, status_code=status.HTTP_201_CREATED)
def create_job_role(body: JobRoleIn, _: User = Depends(manager_only), db: Session = Depends(get_db)):
    role = JobRole(name=body.name.strip())
    db.add(role)
    _conflict_if_duplicate(db, "job role")
    return role


@router.delete("/job-roles/{job_role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_role(job_role_id: uuid.UUID, _: User = Depends(manager_only), db: Session = Depends(get_db)):
    service.delete_job_role(db, job_role_id)


# ---------- staff qualifications ----------

@router.get("/staff/{user_id}/job-roles", response_model=list[JobRoleOut])
def get_staff_job_roles(user_id: uuid.UUID, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service.get_user(db, user_id)
    ids = service.user_job_role_ids(db, user_id)
    if not ids:
        return []
    return db.scalars(select(JobRole).where(JobRole.id.in_(ids)).order_by(JobRole.name)).all()


@router.put("/staff/{user_id}/job-roles", response_model=list[JobRoleOut])
def set_staff_job_roles(
    user_id: uuid.UUID, body: StaffJobRolesIn, _: User = Depends(manager_only), db: Session = Depends(get_db)
):
    return service.set_staff_job_roles(db, user_id, body.job_role_ids)


# ---------- shift types ----------

@router.get("/shift-types", response_model=list[ShiftTypeOut])
def list_shift_types(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(ShiftType).order_by(ShiftType.start_time)).all()


@router.post("/shift-types", response_model=ShiftTypeOut, status_code=status.HTTP_201_CREATED)
def create_shift_type(
    body: ShiftTypeIn = Body(openapi_examples=SHIFT_TYPE_EXAMPLES),
    _: User = Depends(manager_only),
    db: Session = Depends(get_db),
):
    if body.start_time == body.end_time:
        raise RosterError(422, "start_time and end_time cannot be the same")
    if body.job_role_id is not None:
        service.get_job_role(db, body.job_role_id)
    st = ShiftType(**body.model_dump())
    st.name = st.name.strip()
    db.add(st)
    _conflict_if_duplicate(db, "shift type")
    return st


@router.delete("/shift-types/{shift_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shift_type(shift_type_id: uuid.UUID, _: User = Depends(manager_only), db: Session = Depends(get_db)):
    service.delete_shift_type(db, shift_type_id)


# ---------- shifts ----------

@router.post("/shifts", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
def create_shift(
    body: ShiftIn = Body(openapi_examples=SHIFT_EXAMPLES),
    caller: User = Depends(manager_only),
    db: Session = Depends(get_db),
):
    """Rosters a person. Give EITHER shift_type_id + date, OR start_at + end_at (see Examples).

    Rejects double-booking, unqualified staff and invalid times.
    """
    return service.create_shift(db, body, created_by=caller.id)


@router.get("/shifts", response_model=list[ShiftOut])
def list_shifts(
    date_from: date = Query(alias="from", examples=["2026-11-09"]),
    date_to: date = Query(alias="to", examples=["2026-11-15"]),
    user_id: uuid.UUID | None = None,
    caller: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Managers see everyone (optionally one person). Staff only ever see their own shifts."""
    if caller.role == Role.STAFF:
        user_id = caller.id
    return service.list_shifts(db, date_from, date_to, user_id)


@router.get("/shifts/mine", response_model=list[ShiftOut])
def my_shifts(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    caller: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.list_shifts(db, date_from, date_to, caller.id)


@router.delete("/shifts/{shift_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shift(shift_id: uuid.UUID, _: User = Depends(manager_only), db: Session = Depends(get_db)):
    service.delete_shift(db, shift_id)
