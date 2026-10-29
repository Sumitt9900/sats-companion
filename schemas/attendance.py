"""
schemas/attendance.py — Pydantic schemas for Attendance entity.
"""
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from core.models import AttendanceStatus


class AttendanceEntry(BaseModel):
    """Single attendance entry for one student."""

    student_sats_id: str = Field(..., max_length=30)
    status: AttendanceStatus = AttendanceStatus.PRESENT
    remarks: Optional[str] = Field(None, max_length=200)


class BulkAttendanceRequest(BaseModel):
    """Request body for POST /attendance/bulk."""

    attendance_date: date = Field(..., description="Date for which attendance is being marked")
    entries: List[AttendanceEntry] = Field(..., min_length=1, description="List of student attendance entries")


class AttendanceResponse(BaseModel):
    """Response schema for a single attendance record."""

    id: str
    student_sats_id: str
    attendance_date: date
    status: AttendanceStatus
    marked_by_teacher_id: Optional[str] = None
    remarks: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AttendanceSummary(BaseModel):
    """Attendance percentage summary for a student."""

    sats_id: str
    student_name: str
    total_days: int
    present_days: int
    absent_days: int
    holiday_days: int
    attendance_percentage: float


class BulkAttendanceResponse(BaseModel):
    """Response for a bulk attendance mark operation."""

    marked: int
    updated: int
    errors: List[str] = []
