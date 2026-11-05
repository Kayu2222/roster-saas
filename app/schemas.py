"""Request / response shapes. Responses never include password hashes."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Module, Role

# bcrypt only uses the first 72 bytes, so cap length well under that.
Password = Field(min_length=8, max_length=64)


class RegisterCompanyRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    owner_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Password
    modules: list[Module] = Field(min_length=1, description="Any of 'roster', 'resource', 'inventory'")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    modules: list[Module]
    created_at: datetime


class UpdateModulesRequest(BaseModel):
    modules: list[Module] = Field(min_length=1)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    name: str
    role: Role
    is_active: bool
    created_at: datetime


class MeOut(BaseModel):
    user: UserOut
    tenant: TenantOut


class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Password
    role: Role = Role.STAFF
