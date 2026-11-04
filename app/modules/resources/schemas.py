import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.resources.models import BookingStatus, ResourceStatus


class ResourceTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ResourceTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class ResourceIn(BaseModel):
    resource_type_id: uuid.UUID
    name: str = Field(min_length=1, max_length=80)
    location: str | None = Field(default=None, max_length=120)


class ResourceUpdate(BaseModel):
    """Send back the `version` you read. If someone changed the resource since, you get 409."""

    version: int
    name: str | None = Field(default=None, min_length=1, max_length=80)
    location: str | None = Field(default=None, max_length=120)
    status: ResourceStatus | None = None


class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resource_type_id: uuid.UUID
    name: str
    location: str | None
    status: ResourceStatus
    version: int


class BookingIn(BaseModel):
    resource_id: uuid.UUID
    start_at: datetime = Field(examples=["2026-11-10T14:00"])
    end_at: datetime = Field(examples=["2026-11-10T15:00"])
    purpose: str | None = Field(default=None, max_length=500, examples=["Team meeting"])


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resource_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    purpose: str | None
    status: BookingStatus
    booked_by: uuid.UUID
    cancelled_at: datetime | None
