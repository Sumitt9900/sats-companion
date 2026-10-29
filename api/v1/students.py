"""
api/v1/students.py — Student management endpoints.

GET    /api/v1/students            — List students (paginated + filtered)
GET    /api/v1/students/{sats_id}  — Student detail
POST   /api/v1/students            — Enroll student
PUT    /api/v1/students/{sats_id}  — Update student
DELETE /api/v1/students/{sats_id}  — Soft-delete (mark withdrawn)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.databsae import get_db
from core.models import Student, Teacher
from core.security import get_current_teacher, get_admin_teacher
from schemas.student import StudentCreate, StudentUpdate, StudentResponse

router = APIRouter(prefix="/students", tags=["Students"])


def _success(data, message: str = "OK") -> dict:
    return {"status": "success", "message": message, "data": data}


@router.get("", response_model=dict, summary="List students")
def list_students(
    school_dise_code: Optional[str] = Query(None, description="Filter by school DISE code"),
    current_class: Optional[str] = Query(None, description="Filter by class e.g. '8'"),
    section: Optional[str] = Query(None, description="Filter by section e.g. 'A'"),
    gender: Optional[str] = Query(None, description="Filter by gender: male/female/other"),
    caste_category: Optional[str] = Query(None, description="Filter: general/obc/sc/st"),
    is_active: Optional[bool] = Query(True, description="Include only active students"),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """
    Return a paginated list of students.

    Supports multi-dimensional filtering useful for Karnataka school management
    workflows such as caste-based scholarship tracking, class-wise reports,
    and gender parity analysis.
    """
    query = db.query(Student)
    if is_active is not None:
        query = query.filter(Student.is_active == is_active)
    if school_dise_code:
        query = query.filter(Student.school_dise_code == school_dise_code)
    if current_class:
        query = query.filter(Student.current_class == current_class)
    if section:
        query = query.filter(Student.section.ilike(section))
    if gender:
        query = query.filter(Student.gender == gender)
    if caste_category:
        query = query.filter(Student.caste_category == caste_category)

    total = query.count()
    students = query.order_by(Student.name).offset(offset).limit(limit).all()

    return _success(
        {
            "total": total,
            "limit": limit,
            "offset": offset,
            "students": [StudentResponse.model_validate(s).model_dump() for s in students],
        }
    )


@router.get("/{sats_id}", response_model=dict, summary="Student detail")
def get_student(
    sats_id: str,
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """Fetch full profile of a student by their SATS ID."""
    student = db.query(Student).filter(Student.sats_id == sats_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return _success(StudentResponse.model_validate(student).model_dump())


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED, summary="Enroll student")
def enroll_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """
    Enroll a new student into the system.

    The SATS ID must be obtained from the Karnataka SATS portal and must be unique.
    """
    existing = db.query(Student).filter(Student.sats_id == payload.sats_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Student with SATS ID {payload.sats_id} already enrolled",
        )

    # Verify school exists
    from core.models import School  # noqa: PLC0415
    school = db.query(School).filter(School.dise_code == payload.school_dise_code).first()
    if not school:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"School with DISE code {payload.school_dise_code} not found",
        )

    student = Student(**payload.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    return _success(StudentResponse.model_validate(student).model_dump(), "Student enrolled successfully")


@router.put("/{sats_id}", response_model=dict, summary="Update student")
def update_student(
    sats_id: str,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """Update details of an existing student record."""
    student = db.query(Student).filter(Student.sats_id == sats_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(student, field, value)

    db.commit()
    db.refresh(student)
    return _success(StudentResponse.model_validate(student).model_dump(), "Student updated successfully")


@router.delete("/{sats_id}", response_model=dict, summary="Withdraw student (soft delete)")
def withdraw_student(
    sats_id: str,
    db: Session = Depends(get_db),
    _admin: Teacher = Depends(get_admin_teacher),
):
    """
    Mark a student as withdrawn (soft delete — sets is_active=False).

    The student record is preserved for historical reporting.
    **Requires admin privileges.**
    """
    student = db.query(Student).filter(Student.sats_id == sats_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    if not student.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student is already withdrawn")

    student.is_active = False
    db.commit()
    return _success({"sats_id": sats_id, "is_active": False}, "Student marked as withdrawn")
