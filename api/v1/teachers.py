"""
api/v1/teachers.py — Teacher management endpoints.

GET  /api/v1/teachers             — List teachers (filtered)
GET  /api/v1/teachers/me          — Current teacher profile
GET  /api/v1/teachers/{id}        — Teacher detail
POST /api/v1/teachers             — Register teacher
PUT  /api/v1/teachers/{id}        — Update teacher
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.databsae import get_db
from core.models import Teacher
from core.security import get_current_teacher, get_admin_teacher, hash_password
from schemas.teacher import TeacherCreate, TeacherUpdate, TeacherResponse

router = APIRouter(prefix="/teachers", tags=["Teachers"])


def _success(data, message: str = "OK") -> dict:
    return {"status": "success", "message": message, "data": data}


@router.get("", response_model=dict, summary="List teachers")
def list_teachers(
    school_dise_code: Optional[str] = Query(None, description="Filter by school DISE code"),
    district: Optional[str] = Query(None, description="Filter by district (via school join)"),
    designation: Optional[str] = Query(None, description="Filter by designation"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """Return a paginated list of teachers, optionally filtered by school or district."""
    query = db.query(Teacher).filter(Teacher.is_active == True)
    if school_dise_code:
        query = query.filter(Teacher.school_dise_code == school_dise_code)
    if designation:
        query = query.filter(Teacher.designation == designation)
    if district:
        from core.models import School  # noqa: PLC0415
        query = query.join(School, Teacher.school_dise_code == School.dise_code).filter(
            School.district.ilike(f"%{district}%")
        )

    total = query.count()
    teachers = query.offset(offset).limit(limit).all()
    return _success(
        {
            "total": total,
            "limit": limit,
            "offset": offset,
            "teachers": [TeacherResponse.model_validate(t).model_dump() for t in teachers],
        }
    )


@router.get("/me", response_model=dict, summary="Current teacher profile")
def get_me(teacher: Teacher = Depends(get_current_teacher)):
    """Return the full profile of the currently authenticated teacher."""
    return _success(TeacherResponse.model_validate(teacher).model_dump())


@router.get("/{teacher_id}", response_model=dict, summary="Teacher detail")
def get_teacher(
    teacher_id: str,
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """Fetch a teacher's details by their internal UUID."""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")
    return _success(TeacherResponse.model_validate(teacher).model_dump())


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED, summary="Register teacher")
def create_teacher(
    payload: TeacherCreate,
    db: Session = Depends(get_db),
    _admin: Teacher = Depends(get_admin_teacher),
):
    """
    Register a new teacher in the system.

    **Requires admin privileges.** KGID must be unique.
    """
    existing = db.query(Teacher).filter(Teacher.kgid == payload.kgid).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Teacher with KGID {payload.kgid} already registered",
        )

    data = payload.model_dump(exclude={"password"})
    data["hashed_password"] = hash_password(payload.password)
    teacher = Teacher(**data)
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return _success(TeacherResponse.model_validate(teacher).model_dump(), "Teacher registered successfully")


@router.put("/{teacher_id}", response_model=dict, summary="Update teacher")
def update_teacher(
    teacher_id: str,
    payload: TeacherUpdate,
    db: Session = Depends(get_db),
    current_teacher: Teacher = Depends(get_current_teacher),
):
    """
    Update a teacher's profile.

    A teacher can update their own profile; admins can update any teacher.
    Password changes are hashed before storage.
    """
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")

    # Authorization: only self or admin
    if not current_teacher.is_admin and current_teacher.id != teacher_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own profile",
        )

    update_data = payload.model_dump(exclude_none=True)
    if "password" in update_data:
        update_data["hashed_password"] = hash_password(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(teacher, field, value)

    db.commit()
    db.refresh(teacher)
    return _success(TeacherResponse.model_validate(teacher).model_dump(), "Teacher updated successfully")
