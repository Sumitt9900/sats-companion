"""
schemas/school.py — Pydantic schemas for School entity.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from core.models import SchoolType


class SchoolBase(BaseModel):
    """Shared fields for school create / update."""

    name: str = Field(..., max_length=200)
    district: str = Field(..., max_length=100)
    taluk: str = Field(..., max_length=100)
    block: Optional[str] = Field(None, max_length=100)
    village: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = None
    pincode: Optional[str] = Field(None, max_length=10)
    school_type: SchoolType = SchoolType.GOVERNMENT
    medium: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = Field(None, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)


class SchoolCreate(SchoolBase):
    """Request body for creating a school. Requires DISE code."""

    dise_code: str = Field(..., max_length=20, description="Unique DISE school code")


class SchoolUpdate(SchoolBase):
    """Request body for updating a school. All fields optional."""

    name: Optional[str] = Field(None, max_length=200)
    district: Optional[str] = Field(None, max_length=100)
    taluk: Optional[str] = Field(None, max_length=100)
    school_type: Optional[SchoolType] = None


class SchoolResponse(SchoolBase):
    """Response schema for a school record."""

    dise_code: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
