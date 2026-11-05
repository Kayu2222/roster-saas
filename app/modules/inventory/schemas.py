import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.inventory.models import MovementReason


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    unit: str = Field(default="unit", min_length=1, max_length=30, examples=["box"])
    reorder_level: int = Field(default=0, ge=0, description="Show a low-stock warning at or below this")
    opening_stock: int = Field(default=0, ge=0, description="How many you have right now")


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    reorder_level: int | None = Field(default=None, ge=0)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str
    on_hand: int
    reorder_level: int
    low_stock: bool


class ReceiveIn(BaseModel):
    quantity: int = Field(gt=0, le=1_000_000)
    note: str | None = Field(default=None, max_length=500, examples=["Delivery from supplier"])


class UseIn(BaseModel):
    quantity: int = Field(gt=0, le=1_000_000)
    client_id: uuid.UUID | None = Field(default=None, description="Who it was used for, if anyone")
    note: str | None = Field(default=None, max_length=500)


class CountIn(BaseModel):
    """Stocktake: send what you physically counted and what the screen showed when you counted."""

    counted: int = Field(ge=0, le=1_000_000)
    expected: int = Field(ge=0, description="The on-hand number you saw; if stock moved since, you get 409")
    note: str | None = Field(default=None, max_length=500, examples=["Monthly stocktake"])


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    change: int
    balance_after: int
    reason: MovementReason
    client_id: uuid.UUID | None
    note: str | None
    created_by: uuid.UUID
    created_at: datetime
