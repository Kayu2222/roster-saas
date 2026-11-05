"""Resource module tables: things a company books (rooms, beds, vehicles, equipment).

Every table is TenantScoped, so isolation is automatic.
Times are company-local wall-clock times, same as the roster module.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.tenancy import TenantScoped
from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ResourceStatus(str, enum.Enum):
    AVAILABLE = "available"
    OUT_OF_SERVICE = "out_of_service"  # e.g. bed being repaired, van at the mechanic


class BookingStatus(str, enum.Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"  # kept for history, never deleted


class ResourceType(TenantScoped, Base):
    """A category the company defines, e.g. Bed, Meeting room, Van."""

    __tablename__ = "resource_types"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_resource_type_name_per_tenant"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False)


class Resource(TenantScoped, Base):
    """One bookable thing, e.g. 'Bed 3A' or 'Van 2'.

    `version` enables optimistic locking: every UPDATE checks the version it read
    and bumps it. If someone else changed the row in between, the update affects
    0 rows and SQLAlchemy raises StaleDataError instead of silently overwriting.
    """

    __tablename__ = "resources"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_resource_name_per_tenant"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    resource_type_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("resource_types.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[ResourceStatus] = mapped_column(
        Enum(ResourceStatus, native_enum=False, length=20), default=ResourceStatus.AVAILABLE, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    __mapper_args__ = {"version_id_col": version}


class Booking(TenantScoped, Base):
    """A resource reserved for a period of time."""

    __tablename__ = "bookings"
    __table_args__ = (Index("ix_bookings_resource_start", "tenant_id", "resource_id", "start_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    resource_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("resources.id"), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, native_enum=False, length=20), default=BookingStatus.ACTIVE, nullable=False
    )
    booked_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    # Who the booking is for, if it's for a client (a patient's bed, a customer's room).
    client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("clients.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    resource: Mapped[Resource] = relationship(lazy="joined")
