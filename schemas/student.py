"""
schemas/student.py — Pydantic schemas for Student entity.
"""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field
from core.models import Gender, CasteCategory


class StudentBase(BaseModel):
    """Shared student fields."""

    name: str = Field(..., max_length=150)
    dob: Optional[date] = None
    gender: Gender
    current_class: str = Field(..., max_length=10, description='Class / grade e.g. "8" or "10A"')
    section: Optional[str] = Field(None, max_length=5)
    school_dise_code: str = Field(..., max_length=20)
    aadhaar: Optional[str] = Field(None, max_length=12, description="Aadhaar number (optional)")
    caste_category: CasteCategory = CasteCategory.GENERAL
    religion: Optional[str] = Field(None, max_length=50)
    father_name: Optional[str] = Field(None, max_length=150)
    mother_name: Optional[str] = Field(None, max_length=150)
    guardian_name: Optional[str] = Field(None, max_length=150)
    guardian_phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None


class StudentCreate(StudentBase):
    """Request body for enrolling a new student."""

    sats_id: str = Field(..., max_length=30, description="SATS portal-assigned unique student ID")


class StudentUpdate(BaseModel):
    """Request body for updating a student. All fields optional."""

    name: Optional[str] = Field(None, max_length=150)
    dob: Optional[date] = None
    gender: Optional[Gender] = None
    current_class: Optional[str] = Field(None, max_length=10)
    section: Optional[str] = Field(None, max_length=5)
    school_dise_code: Optional[str] = Field(None, max_length=20)
    aadhaar: Optional[str] = Field(None, max_length=12)
    caste_category: Optional[CasteCategory] = None
    religion: Optional[str] = Field(None, max_length=50)
    father_name: Optional[str] = Field(None, max_length=150)
    mother_name: Optional[str] = Field(None, max_length=150)
    guardian_name: Optional[str] = Field(None, max_length=150)
    guardian_phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None


class StudentResponse(StudentBase):
    """Response schema for a student record."""

    sats_id: str
    is_active: bool
    is_transferred: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
