import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.tenancy import TenantScoped
from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Module(str, enum.Enum):
    """Features a company can switch on when it signs up."""

    ROSTER = "roster"      # staff, shifts, scheduling
    RESOURCE = "resource"  # rooms, beds, vehicles, equipment + bookings


class Role(str, enum.Enum):
    OWNER = "owner"      # created the company; can change modules
    MANAGER = "manager"  # manages staff, rosters and resources
    STAFF = "staff"      # sees own shifts / bookings


class Tenant(Base):
    """A company. NOT tenant-scoped itself; it is the tenant."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    roster_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resource_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    def has_module(self, module: Module) -> bool:
        return {Module.ROSTER: self.roster_enabled, Module.RESOURCE: self.resource_enabled}[module]

    @property
    def modules(self) -> list[Module]:
        return [m for m in Module if self.has_module(m)]


class User(TenantScoped, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Email is unique across the whole platform: one login = one company (MVP decision).
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
