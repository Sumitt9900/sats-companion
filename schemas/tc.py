"""
schemas/tc.py — Pydantic schemas for Transfer Certificate entity.
"""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field
from core.models import TCStatus


class TCRequest(BaseModel):
    """Request body for POST /tc/request."""

    student_sats_id: str = Field(..., max_length=30)
    issuing_school_dise: str = Field(..., max_length=20)
    receiving_school_dise: Optional[str] = Field(None, max_length=20)
    reason: Optional[str] = None
    request_date: Optional[date] = None


class TCApproval(BaseModel):
    """Request body for PUT /tc/{tc_id}/approve."""

    status: TCStatus = Field(default=TCStatus.APPROVED, description="New status — typically 'approved' or 'rejected'")
    tc_number: Optional[str] = Field(None, max_length=50, description="Official TC serial number (on approval)")
    issue_date: Optional[date] = None
    remarks: Optional[str] = None


class TCResponse(BaseModel):
    """Response schema for a Transfer Certificate record."""

    id: str
    student_sats_id: str
    issuing_school_dise: str
    receiving_school_dise: Optional[str] = None
    reason: Optional[str] = None
    status: TCStatus
    requested_by_teacher_id: Optional[str] = None
    approved_by_teacher_id: Optional[str] = None
    request_date: date
    approval_date: Optional[date] = None
    issue_date: Optional[date] = None
    tc_number: Optional[str] = None
    remarks: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
