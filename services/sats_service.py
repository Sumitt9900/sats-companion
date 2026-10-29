"""
services/sats_service.py — Business logic helpers for SATS Companion.

Contains reusable query helpers and calculation utilities shared across
multiple API endpoint modules.
"""
from datetime import date
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from core.models import (
    Student, Attendance, Assessment, AttendanceStatus,
    School, Teacher
)


# ---------------------------------------------------------------------------
# Attendance helpers
# ---------------------------------------------------------------------------

def get_attendance_summary(db: Session, sats_id: str) -> Dict:
    """
    Compute attendance statistics for a student across all recorded dates.

    Args:
        db: SQLAlchemy session.
        sats_id: Student's SATS ID.

    Returns:
        Dict with total_days, present_days, absent_days, holiday_days,
        attendance_percentage, and basic student info.
    """
    student = db.query(Student).filter(Student.sats_id == sats_id).first()
    if not student:
        return {}

    records = db.query(Attendance).filter(
        Attendance.student_sats_id == sats_id
    ).all()

    total = len(records)
    present = sum(1 for r in records if r.status == AttendanceStatus.PRESENT)
    absent = sum(1 for r in records if r.status == AttendanceStatus.ABSENT)
    holiday = sum(1 for r in records if r.status == AttendanceStatus.HOLIDAY)
    half_day = sum(1 for r in records if r.status == AttendanceStatus.HALF_DAY)

    # Attendance percentage: present + half_day*0.5 over non-holiday days
    eligible_days = total - holiday
    effective_present = present + (half_day * 0.5)
    percentage = round((effective_present / eligible_days * 100) if eligible_days > 0 else 0.0, 2)

    return {
        "sats_id": sats_id,
        "student_name": student.name,
        "total_days": total,
        "present_days": present,
        "absent_days": absent,
        "holiday_days": holiday,
        "half_day": half_day,
        "attendance_percentage": percentage,
    }


def get_at_risk_students(
    db: Session,
    school_dise_code: Optional[str] = None,
    current_class: Optional[str] = None,
    threshold: float = 75.0,
) -> List[Dict]:
    """
    Return students whose attendance percentage is below *threshold*.

    Args:
        db: SQLAlchemy session.
        school_dise_code: Filter to a specific school.
        current_class: Filter to a specific class.
        threshold: Minimum acceptable attendance % (default 75).

    Returns:
        List of student attendance summary dicts below the threshold.
    """
    query = db.query(Student).filter(Student.is_active == True)
    if school_dise_code:
        query = query.filter(Student.school_dise_code == school_dise_code)
    if current_class:
        query = query.filter(Student.current_class == current_class)

    students = query.all()
    at_risk = []
    for student in students:
        summary = get_attendance_summary(db, student.sats_id)
        if summary and summary["attendance_percentage"] < threshold:
            summary["gender"] = student.gender.value if student.gender else None
            summary["caste_category"] = student.caste_category.value if student.caste_category else None
            summary["current_class"] = student.current_class
            at_risk.append(summary)

    return at_risk


# ---------------------------------------------------------------------------
# Assessment helpers
# ---------------------------------------------------------------------------

def get_student_assessment_summary(db: Session, sats_id: str) -> List[Dict]:
    """
    Return per-subject assessment summary for a student.

    Args:
        db: SQLAlchemy session.
        sats_id: Student's SATS ID.

    Returns:
        List of SubjectSummary-compatible dicts.
    """
    records = db.query(Assessment).filter(
        Assessment.student_sats_id == sats_id
    ).all()

    subject_map: Dict[str, List[Assessment]] = {}
    for rec in records:
        subject_map.setdefault(rec.subject, []).append(rec)

    summaries = []
    for subject, items in subject_map.items():
        percentages = [
            round((r.marks_obtained / r.max_marks * 100), 2) for r in items if r.max_marks > 0
        ]
        weak_chapters = [
            r.chapter for r in items
            if r.chapter and r.max_marks > 0 and (r.marks_obtained / r.max_marks * 100) < 50
        ]
        summaries.append({
            "subject": subject,
            "assessment_count": len(items),
            "average_percentage": round(sum(percentages) / len(percentages), 2) if percentages else 0.0,
            "highest_percentage": max(percentages) if percentages else 0.0,
            "lowest_percentage": min(percentages) if percentages else 0.0,
            "weak_chapters": list(set(weak_chapters)),
        })

    return summaries


def get_class_assessment_report(
    db: Session,
    school_dise_code: str,
    current_class: str,
    section: Optional[str] = None,
    subject: Optional[str] = None,
    academic_year: Optional[str] = None,
) -> List[Dict]:
    """
    Return per-student assessment summaries for an entire class.

    Useful for class-level AI reports and teacher dashboards.
    """
    student_query = db.query(Student).filter(
        Student.school_dise_code == school_dise_code,
        Student.current_class == current_class,
        Student.is_active == True,
    )
    if section:
        student_query = student_query.filter(Student.section == section)
    students = student_query.all()

    results = []
    for student in students:
        assessment_query = db.query(Assessment).filter(
            Assessment.student_sats_id == student.sats_id
        )
        if subject:
            assessment_query = assessment_query.filter(Assessment.subject == subject)
        if academic_year:
            assessment_query = assessment_query.filter(Assessment.academic_year == academic_year)

        records = assessment_query.all()
        percentages = [
            round((r.marks_obtained / r.max_marks * 100), 2) for r in records if r.max_marks > 0
        ]
        results.append({
            "sats_id": student.sats_id,
            "name": student.name,
            "gender": student.gender.value if student.gender else None,
            "caste_category": student.caste_category.value if student.caste_category else None,
            "assessment_count": len(records),
            "average_percentage": round(sum(percentages) / len(percentages), 2) if percentages else 0.0,
        })

    return results


def get_weak_chapters_for_subject(
    db: Session,
    subject: str,
    school_dise_code: str,
    current_class: str,
    threshold_pct: float = 50.0,
) -> List[str]:
    """
    Return chapters in *subject* where the class average is below *threshold_pct*.

    Args:
        db: SQLAlchemy session.
        subject: Subject name.
        school_dise_code: Filter to school.
        current_class: Filter to class.
        threshold_pct: Chapter is 'weak' if class average below this value.

    Returns:
        List of chapter names.
    """
    student_ids = [
        s.sats_id for s in db.query(Student.sats_id).filter(
            Student.school_dise_code == school_dise_code,
            Student.current_class == current_class,
            Student.is_active == True,
        ).all()
    ]

    records = db.query(Assessment).filter(
        Assessment.student_sats_id.in_(student_ids),
        Assessment.subject == subject,
        Assessment.chapter.isnot(None),
    ).all()

    chapter_map: Dict[str, List[float]] = {}
    for rec in records:
        if rec.max_marks > 0 and rec.chapter:
            pct = rec.marks_obtained / rec.max_marks * 100
            chapter_map.setdefault(rec.chapter, []).append(pct)

    weak = [
        ch for ch, pcts in chapter_map.items()
        if (sum(pcts) / len(pcts)) < threshold_pct
    ]
    return weak
