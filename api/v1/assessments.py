"""
api/v1/assessments.py — Assessment management endpoints.

POST /api/v1/assessments                        — Record an assessment
GET  /api/v1/assessments/student/{sats_id}      — All assessments for a student
GET  /api/v1/assessments/report                 — Class-level report
GET  /api/v1/assessments/subject/{subject}/summary — Subject-wise summary
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.databsae import get_db
from core.models import Assessment, Student, Teacher
from core.security import get_current_teacher
from schemas.assessment import AssessmentCreate, AssessmentResponse, SubjectSummary
from services.sats_service import (
    get_student_assessment_summary,
    get_class_assessment_report,
    get_weak_chapters_for_subject,
)

router = APIRouter(prefix="/assessments", tags=["Assessments"])


def _success(data, message: str = "OK") -> dict:
    return {"status": "success", "message": message, "data": data}


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED, summary="Record assessment")
def record_assessment(
    payload: AssessmentCreate,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Record a new assessment result for a student.

    Supports FA1–FA4 and SA1–SA2 types as per Karnataka KSEEB norms,
    as well as unit tests, quarterly, and half-yearly exams.
    """
    student = db.query(Student).filter(
        Student.sats_id == payload.student_sats_id,
        Student.is_active == True,
    ).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found or inactive")

    data = payload.model_dump()
    data["recorded_by_teacher_id"] = teacher.id
    assessment = Assessment(**data)
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    response_data = AssessmentResponse.model_validate(assessment).model_dump()
    response_data["percentage"] = assessment.percentage
    return _success(response_data, "Assessment recorded successfully")


@router.get("/student/{sats_id}", response_model=dict, summary="Assessments for a student")
def get_student_assessments(
    sats_id: str,
    subject: Optional[str] = Query(None),
    assessment_type: Optional[str] = Query(None),
    academic_year: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """Return all assessment records for a given student, with optional filters."""
    student = db.query(Student).filter(Student.sats_id == sats_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    query = db.query(Assessment).filter(Assessment.student_sats_id == sats_id)
    if subject:
        query = query.filter(Assessment.subject.ilike(f"%{subject}%"))
    if assessment_type:
        query = query.filter(Assessment.assessment_type == assessment_type)
    if academic_year:
        query = query.filter(Assessment.academic_year == academic_year)

    total = query.count()
    records = query.order_by(Assessment.assessment_date.desc()).offset(offset).limit(limit).all()

    result_items = []
    for r in records:
        item = AssessmentResponse.model_validate(r).model_dump()
        item["percentage"] = r.percentage
        result_items.append(item)

    return _success(
        {
            "student": {"sats_id": student.sats_id, "name": student.name},
            "total": total,
            "limit": limit,
            "offset": offset,
            "assessments": result_items,
            "subject_summaries": get_student_assessment_summary(db, sats_id),
        }
    )


@router.get("/report", response_model=dict, summary="Class-level assessment report")
def class_assessment_report(
    school_dise_code: str = Query(..., description="School DISE code"),
    current_class: str = Query(..., description="Class e.g. '8'"),
    section: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    academic_year: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """
    Generate a class-level assessment report.

    Returns per-student summary statistics useful for teacher dashboards
    and AI class-summary generation.
    """
    results = get_class_assessment_report(
        db, school_dise_code, current_class, section, subject, academic_year
    )
    if not results:
        return _success({"students": [], "class_average": 0.0}, "No data found")

    avg = sum(r["average_percentage"] for r in results) / len(results)
    return _success(
        {
            "school_dise_code": school_dise_code,
            "current_class": current_class,
            "section": section,
            "subject_filter": subject,
            "class_average_percentage": round(avg, 2),
            "students": results,
        }
    )


@router.get("/subject/{subject}/summary", response_model=dict, summary="Subject-wise summary")
def subject_summary(
    subject: str,
    school_dise_code: str = Query(...),
    current_class: str = Query(...),
    academic_year: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """
    Return subject-level performance analysis for a class.

    Highlights weak chapters — chapters where the class average is below 50%.
    """
    results = get_class_assessment_report(
        db, school_dise_code, current_class, None, subject, academic_year
    )
    if not results:
        return _success({"subject": subject, "data": []}, "No assessment data found for this subject")

    percentages = [r["average_percentage"] for r in results if r["assessment_count"] > 0]
    weak_chapters = get_weak_chapters_for_subject(db, subject, school_dise_code, current_class)

    return _success(
        {
            "subject": subject,
            "school_dise_code": school_dise_code,
            "current_class": current_class,
            "student_count": len(results),
            "class_average_percentage": round(sum(percentages) / len(percentages), 2) if percentages else 0.0,
            "highest_student_avg": max(percentages) if percentages else 0.0,
            "lowest_student_avg": min(percentages) if percentages else 0.0,
            "weak_chapters": weak_chapters,
            "students": results,
        }
    )
