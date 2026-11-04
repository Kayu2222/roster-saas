import uuid
from datetime import date as Date
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobRoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class JobRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class StaffJobRolesIn(BaseModel):
    job_role_ids: list[uuid.UUID] = Field(description="Replaces the person's qualifications. Empty list clears them.")


class ShiftTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    start_time: time = Field(examples=["07:00"])
    end_time: time = Field(examples=["15:00"], description="Earlier than or equal to start_time means overnight")
    job_role_id: uuid.UUID | None = None


class ShiftTypeOut(ShiftTypeIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    overnight: bool


class ShiftIn(BaseModel):
    """Either give a shift type + date, or give exact start/end times."""

    user_id: uuid.UUID
    shift_type_id: uuid.UUID | None = None
    date: Date | None = Field(default=None, description="Required with shift_type_id")
    start_at: datetime | None = Field(default=None, description="Required without shift_type_id")
    end_at: datetime | None = None
    job_role_id: uuid.UUID | None = Field(default=None, description="Overrides the shift type's role")
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _one_way_to_set_times(self):
        if self.shift_type_id is not None:
            if self.date is None:
                raise ValueError("date is required when using shift_type_id")
            if self.start_at or self.end_at:
                raise ValueError("give either shift_type_id + date, or start_at + end_at, not both")
        else:
            if self.start_at is None or self.end_at is None:
                raise ValueError("start_at and end_at are required without shift_type_id")
        return self


class ShiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    shift_type_id: uuid.UUID | None
    job_role_id: uuid.UUID | None
    notes: str | None
    created_by: uuid.UUID
