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
    attendance_date: Optional[date] = None   # Per-entry date (overrides bulk date if set)
    status: AttendanceStatus = AttendanceStatus.PRESENT
    remarks: Optional[str] = Field(None, max_length=200)


class BulkAttendanceRequest(BaseModel):
    """Request body for POST /attendance/bulk.

    Accepts either ``entries`` or ``records`` as the list key for compatibility
    with the PWA frontend (which sends ``records``).
    """

    attendance_date: date = Field(..., description="Date for which attendance is being marked")
    entries: Optional[List[AttendanceEntry]] = Field(None, description="List of student attendance entries")
    records: Optional[List[AttendanceEntry]] = Field(None, description="Alias for entries (PWA compatibility)")

    @property
    def all_entries(self) -> List[AttendanceEntry]:
        """Return whichever of entries/records was provided."""
        return self.entries or self.records or []


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
