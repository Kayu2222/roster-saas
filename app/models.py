import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, String, Text, Uuid, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.tenancy import TenantScoped
from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Module(str, enum.Enum):
    """Features a company can switch on when it signs up."""

    ROSTER = "roster"      # staff, shifts, scheduling
    RESOURCE = "resource"  # assets: rooms, beds, vehicles, booked by time
    INVENTORY = "inventory"  # products: medicine, supplies, used up by quantity


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
    # server_default so the migration can add it to existing companies (switched off).
    inventory_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    _FLAGS = {Module.ROSTER: "roster_enabled", Module.RESOURCE: "resource_enabled", Module.INVENTORY: "inventory_enabled"}

    def has_module(self, module: Module) -> bool:
        return getattr(self, self._FLAGS[module])

    def set_modules(self, modules: list[Module]) -> None:
        for module, flag in self._FLAGS.items():
            setattr(self, flag, module in modules)

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


class Client(TenantScoped, Base):
    """Someone the company serves who does not sign in: a patient, customer, student or guest.

    Deliberately minimal (data minimisation): contact details and a short note only.
    No medical or other sensitive fields, so the product stays general-purpose.
    """

    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
