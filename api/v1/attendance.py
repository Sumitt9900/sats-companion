"""
api/v1/attendance.py — Attendance management endpoints.

POST /api/v1/attendance/bulk          — Mark bulk attendance
GET  /api/v1/attendance/report        — Attendance report
GET  /api/v1/attendance/summary/{id}  — Per-student attendance summary
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from core.databsae import get_db
from core.models import Attendance, Student, Teacher, AttendanceStatus
from core.security import get_current_teacher
from schemas.attendance import (
    BulkAttendanceRequest,
    AttendanceResponse,
    AttendanceSummary,
    BulkAttendanceResponse,
)
from services.sats_service import get_attendance_summary

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def _success(data, message: str = "OK") -> dict:
    return {"status": "success", "message": message, "data": data}


@router.post("/bulk", response_model=dict, summary="Mark bulk attendance")
def mark_bulk_attendance(
    payload: BulkAttendanceRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Mark attendance for multiple students in a single request.

    - Existing records for the same student + date are **updated** (upsert).
    - Invalid SATS IDs are reported in the `errors` list.
    - The teacher marking attendance is recorded against each entry.
    """
    marked = 0
    updated = 0
    errors = []

    for entry in payload.all_entries:
        student = db.query(Student).filter(
            Student.sats_id == entry.student_sats_id,
            Student.is_active == True,
        ).first()
        if not student:
            errors.append(f"Student {entry.student_sats_id} not found or inactive")
            continue

        existing = db.query(Attendance).filter(
            Attendance.student_sats_id == entry.student_sats_id,
            Attendance.attendance_date == (entry.attendance_date or payload.attendance_date),
        ).first()

        att_date = entry.attendance_date or payload.attendance_date

        if existing:
            existing.status = entry.status
            existing.remarks = entry.remarks
            existing.marked_by_teacher_id = teacher.id
            updated += 1
        else:
            record = Attendance(
                student_sats_id=entry.student_sats_id,
                attendance_date=att_date,
                status=entry.status,
                remarks=entry.remarks,
                marked_by_teacher_id=teacher.id,
            )
            db.add(record)
            marked += 1

    db.commit()
    return _success(
        {"marked": marked, "updated": updated, "errors": errors},
        f"Attendance processed: {marked} new, {updated} updated",
    )


@router.get("/report", response_model=dict, summary="Attendance report")
def attendance_report(
    school_dise_code: Optional[str] = Query(None),
    current_class: Optional[str] = Query(None, description="Filter by class e.g. '8'"),
    section: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    sats_id: Optional[str] = Query(None, description="Filter to a specific student"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """
    Generate an attendance report filtered by school, class, date range, or student.

    Returns raw attendance records sorted by date descending.
    """
    query = db.query(Attendance)

    if sats_id:
        query = query.filter(Attendance.student_sats_id == sats_id)
    elif school_dise_code or current_class or section:
        student_query = db.query(Student.sats_id).filter(Student.is_active == True)
        if school_dise_code:
            student_query = student_query.filter(Student.school_dise_code == school_dise_code)
        if current_class:
            student_query = student_query.filter(Student.current_class == current_class)
        if section:
            student_query = student_query.filter(Student.section.ilike(section))
        sats_ids = [row[0] for row in student_query.all()]
        query = query.filter(Attendance.student_sats_id.in_(sats_ids))

    if from_date:
        query = query.filter(Attendance.attendance_date >= from_date)
    if to_date:
        query = query.filter(Attendance.attendance_date <= to_date)

    total = query.count()
    records = query.order_by(Attendance.attendance_date.desc()).offset(offset).limit(limit).all()

    return _success(
        {
            "total": total,
            "limit": limit,
            "offset": offset,
            "records": [AttendanceResponse.model_validate(r).model_dump() for r in records],
        }
    )


@router.get("/summary/{sats_id}", response_model=dict, summary="Student attendance summary")
def student_attendance_summary(
    sats_id: str,
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """
    Return attendance percentage and statistics for a specific student.

    Attendance percentage is calculated as:
    (present_days + half_day × 0.5) / (total_days − holiday_days) × 100
    """
    summary = get_attendance_summary(db, sats_id)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return _success(summary)
