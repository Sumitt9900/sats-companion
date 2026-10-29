"""
api/v1/ai_insights.py — Google Gemini AI-powered insight endpoints.

POST /api/v1/ai/student-report/{sats_id}  — Student performance report
POST /api/v1/ai/class-summary             — Class performance summary
POST /api/v1/ai/attendance-alert          — Attendance risk analysis
POST /api/v1/ai/lesson-plan               — Lesson plan suggestions
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.config import settings
from core.databsae import get_db
from core.models import Student, Teacher, School
from core.security import get_current_teacher
from services.ai_service import (
    generate_student_report,
    generate_class_summary,
    generate_attendance_alert,
    generate_lesson_plan,
)
from services.sats_service import (
    get_attendance_summary,
    get_student_assessment_summary,
    get_class_assessment_report,
    get_at_risk_students,
    get_weak_chapters_for_subject,
)

router = APIRouter(prefix="/ai", tags=["AI Insights (Gemini)"])


def _success(data, message: str = "OK") -> dict:
    return {"status": "success", "message": message, "data": data}


def _require_api_key():
    """Raise 503 if Gemini API key is not configured."""
    if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == "your-gemini-api-key-here":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API key not configured. Set GOOGLE_API_KEY in .env",
        )


# ---------------------------------------------------------------------------
# Request body schemas (local — simple, only used in AI endpoints)
# ---------------------------------------------------------------------------

class ClassSummaryRequest(BaseModel):
    school_dise_code: str
    current_class: str
    section: Optional[str] = None
    academic_year: Optional[str] = None
    subject: Optional[str] = None


class AttendanceAlertRequest(BaseModel):
    school_dise_code: Optional[str] = None
    current_class: Optional[str] = None
    threshold_percentage: float = Field(75.0, ge=0, le=100)


class LessonPlanRequest(BaseModel):
    subject: str
    school_dise_code: str
    current_class: str
    academic_year: str = Field(..., examples=["2024-25"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/student-report/{sats_id}",
    response_model=dict,
    summary="AI student performance report",
)
def ai_student_report(
    sats_id: str,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Generate an AI-powered personalised performance report for a student.

    Uses Google Gemini to analyse attendance and assessment data and produce
    a teacher-ready narrative with Karnataka curriculum-aligned recommendations.
    """
    _require_api_key()

    student = db.query(Student).filter(Student.sats_id == sats_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    # Gather data
    attendance = get_attendance_summary(db, sats_id)
    from core.models import Assessment  # noqa: PLC0415
    assessments_raw = db.query(Assessment).filter(Assessment.student_sats_id == sats_id).all()
    assessments = [
        {
            "subject": a.subject,
            "assessment_type": a.assessment_type.value,
            "marks_obtained": a.marks_obtained,
            "max_marks": a.max_marks,
            "percentage": a.percentage,
            "chapter": a.chapter,
            "assessment_date": str(a.assessment_date),
        }
        for a in assessments_raw
    ]

    student_data = {
        "name": student.name,
        "current_class": student.current_class,
        "section": student.section,
        "school_dise_code": student.school_dise_code,
        "gender": student.gender.value if student.gender else None,
        "caste_category": student.caste_category.value if student.caste_category else None,
    }

    try:
        report_text = generate_student_report(student_data, assessments, attendance)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini API error: {str(exc)}",
        )

    return _success(
        {
            "sats_id": sats_id,
            "student_name": student.name,
            "report": report_text,
            "data_snapshot": {
                "attendance": attendance,
                "assessment_count": len(assessments),
            },
        },
        "AI student report generated successfully",
    )


@router.post("/class-summary", response_model=dict, summary="AI class performance summary")
def ai_class_summary(
    payload: ClassSummaryRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Generate an AI-powered class-level performance summary.

    Analyses all students in the specified class and produces strategic
    teaching recommendations aligned with Karnataka KSEEB standards.
    """
    _require_api_key()

    school = db.query(School).filter(School.dise_code == payload.school_dise_code).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")

    students_data = get_class_assessment_report(
        db,
        payload.school_dise_code,
        payload.current_class,
        payload.section,
        payload.subject,
        payload.academic_year,
    )

    if not students_data:
        return _success(
            {"summary": "No assessment data available for this class yet."},
            "Insufficient data for AI summary",
        )

    class_data = {
        "current_class": payload.current_class,
        "section": payload.section,
        "school_dise_code": payload.school_dise_code,
    }

    try:
        summary_text = generate_class_summary(class_data, students_data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini API error: {str(exc)}",
        )

    return _success(
        {
            "school": payload.school_dise_code,
            "current_class": payload.current_class,
            "section": payload.section,
            "student_count": len(students_data),
            "summary": summary_text,
        },
        "AI class summary generated",
    )


@router.post("/attendance-alert", response_model=dict, summary="AI attendance risk analysis")
def ai_attendance_alert(
    payload: AttendanceAlertRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Identify students at attendance risk and generate AI-powered intervention guidance.

    Students below the threshold (default 75%) are flagged and analysed in the
    context of Karnataka's rural and semi-urban government school environment.
    """
    _require_api_key()

    at_risk = get_at_risk_students(
        db,
        school_dise_code=payload.school_dise_code,
        current_class=payload.current_class,
        threshold=payload.threshold_percentage,
    )

    if not at_risk:
        return _success(
            {
                "at_risk_count": 0,
                "alert": "Great news! No students are below the attendance threshold.",
            },
            "No attendance alerts",
        )

    school_info = {}
    if payload.school_dise_code:
        school = db.query(School).filter(School.dise_code == payload.school_dise_code).first()
        if school:
            school_info = {
                "name": school.name,
                "district": school.district,
                "school_type": school.school_type.value if school.school_type else None,
            }

    try:
        alert_text = generate_attendance_alert(at_risk, school_info)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini API error: {str(exc)}",
        )

    return _success(
        {
            "at_risk_count": len(at_risk),
            "threshold_percentage": payload.threshold_percentage,
            "at_risk_students": at_risk,
            "ai_analysis": alert_text,
        },
        f"{len(at_risk)} student(s) flagged as attendance risk",
    )


@router.post("/lesson-plan", response_model=dict, summary="AI lesson plan suggestions")
def ai_lesson_plan(
    payload: LessonPlanRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Generate a 2-week lesson plan tailored to the class's weak areas.

    The AI uses chapter-level weak area data from assessments to produce
    a practical, KSEEB-aligned lesson plan for the requesting teacher.
    """
    _require_api_key()

    weak_chapters = get_weak_chapters_for_subject(
        db,
        payload.subject,
        payload.school_dise_code,
        payload.current_class,
    )

    if not weak_chapters:
        weak_chapters = ["(General — no specific weak chapters identified; plan for overall revision)"]

    try:
        plan_text = generate_lesson_plan(
            subject=payload.subject,
            current_class=payload.current_class,
            weak_chapters=weak_chapters,
            teacher_name=teacher.name,
            academic_year=payload.academic_year,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini API error: {str(exc)}",
        )

    return _success(
        {
            "subject": payload.subject,
            "current_class": payload.current_class,
            "school_dise_code": payload.school_dise_code,
            "weak_chapters_identified": weak_chapters,
            "lesson_plan": plan_text,
        },
        "AI lesson plan generated successfully",
    )
