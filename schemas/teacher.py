"""
schemas/teacher.py — Pydantic schemas for Teacher entity.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from core.models import Designation


class TeacherBase(BaseModel):
    """Shared teacher fields."""

    name: str = Field(..., max_length=150)
    designation: Designation = Designation.ASST_TEACHER
    subject: Optional[str] = Field(None, max_length=100)
    school_dise_code: Optional[str] = Field(None, max_length=20)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)


class TeacherCreate(TeacherBase):
    """Request body for registering a new teacher."""

    kgid: str = Field(..., max_length=20, description="Karnataka Government ID (employee ID)")
    password: str = Field(..., min_length=8, description="Initial password for the teacher")


class TeacherUpdate(BaseModel):
    """Request body for updating a teacher. All fields optional."""

    name: Optional[str] = Field(None, max_length=150)
    designation: Optional[Designation] = None
    subject: Optional[str] = Field(None, max_length=100)
    school_dise_code: Optional[str] = Field(None, max_length=20)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    password: Optional[str] = Field(None, min_length=8)


class TeacherResponse(TeacherBase):
    """Response schema for a teacher record (password excluded)."""

    id: str
    kgid: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
