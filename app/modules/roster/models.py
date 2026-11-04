"""Roster module tables. Every table is TenantScoped, so isolation is automatic.

Times are stored as the company's local wall-clock time (no timezone).
A per-company timezone setting can be added later without changing these tables.
"""

import uuid
from datetime import datetime, time

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Time, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.tenancy import TenantScoped
from app.db import Base


class JobRole(TenantScoped, Base):
    """A job title the company defines itself, e.g. Nurse, Barista, Forklift Driver."""

    __tablename__ = "job_roles"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_job_role_name_per_tenant"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False)


class StaffJobRole(TenantScoped, Base):
    """Which job roles a person is qualified for (a person can hold several)."""

    __tablename__ = "staff_job_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    job_role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("job_roles.id", ondelete="CASCADE"), primary_key=True
    )


class ShiftType(TenantScoped, Base):
    """A reusable shift template, e.g. 'Morning 07:00-15:00' or 'Night 22:00-06:00'.

    If end_time <= start_time the shift runs overnight into the next day.
    """

    __tablename__ = "shift_types"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_shift_type_name_per_tenant"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    # Optional: only people holding this job role can work this shift type.
    job_role_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("job_roles.id"), nullable=True)

    @property
    def overnight(self) -> bool:
        return self.end_time <= self.start_time


class Shift(TenantScoped, Base):
    """One person working one block of time."""

    __tablename__ = "shifts"
    __table_args__ = (Index("ix_shifts_user_start", "tenant_id", "user_id", "start_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    shift_type_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("shift_types.id"), nullable=True)
    job_role_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("job_roles.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)

    shift_type: Mapped[ShiftType | None] = relationship(lazy="joined")
    job_role: Mapped[JobRole | None] = relationship(lazy="joined")
