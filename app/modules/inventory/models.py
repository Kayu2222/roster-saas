"""Inventory: products that get used up by quantity (medicine, supplies, stock).

Two tables:
- products: what you stock, and how many are on hand right now.
- stock_movements: an append-only ledger. Every change to on_hand writes one row
  (received, used, counted), so the current number can always be explained.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.tenancy import TenantScoped
from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MovementReason(str, enum.Enum):
    RECEIVED = "received"  # delivery came in (+)
    USED = "used"          # given out or consumed, optionally for a client (-)
    COUNTED = "counted"    # stocktake correction (+ or -)


class Product(TenantScoped, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_product_name_per_tenant"),
        # The database refuses negative stock, whatever the application does.
        CheckConstraint("on_hand >= 0", name="ck_products_on_hand_not_negative"),
        CheckConstraint("reorder_level >= 0", name="ck_products_reorder_level_not_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="unit")  # box, tablet, kg...
    on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reorder_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # warn at or below this
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    @property
    def low_stock(self) -> bool:
        return self.on_hand <= self.reorder_level


class StockMovement(TenantScoped, Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("change <> 0", name="ck_stock_movements_change_not_zero"),
        CheckConstraint("balance_after >= 0", name="ck_stock_movements_balance_not_negative"),
        Index("ix_stock_movements_product_created", "tenant_id", "product_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    change: Mapped[int] = mapped_column(Integer, nullable=False)          # +received, -used
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)   # on_hand right after this change
    reason: Mapped[MovementReason] = mapped_column(Enum(MovementReason, native_enum=False, length=20), nullable=False)
    client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("clients.id"), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    product: Mapped[Product] = relationship(lazy="joined")
