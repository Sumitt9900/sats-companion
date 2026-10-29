"""
api/v1/schools.py — School management endpoints.

GET  /api/v1/schools              — List all schools (paginated)
GET  /api/v1/schools/{dise_code}  — School detail
POST /api/v1/schools              — Create school (admin)
PUT  /api/v1/schools/{dise_code}  — Update school
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.databsae import get_db
from core.models import School, Teacher
from core.security import get_current_teacher, get_admin_teacher
from schemas.school import SchoolCreate, SchoolUpdate, SchoolResponse

router = APIRouter(prefix="/schools", tags=["Schools"])


def _success(data, message: str = "OK") -> dict:
    return {"status": "success", "message": message, "data": data}


@router.get("", response_model=dict, summary="List all schools")
def list_schools(
    district: Optional[str] = Query(None, description="Filter by district name"),
    taluk: Optional[str] = Query(None, description="Filter by taluk name"),
    school_type: Optional[str] = Query(None, description="Filter by type: government/aided/unaided"),
    limit: int = Query(20, ge=1, le=200, description="Max records per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """
    Return a paginated list of Karnataka schools.

    Supports filtering by **district**, **taluk**, and **school_type**.
    """
    query = db.query(School).filter(School.is_active == True)
    if district:
        query = query.filter(School.district.ilike(f"%{district}%"))
    if taluk:
        query = query.filter(School.taluk.ilike(f"%{taluk}%"))
    if school_type:
        query = query.filter(School.school_type == school_type)

    total = query.count()
    schools = query.offset(offset).limit(limit).all()

    return _success(
        {
            "total": total,
            "limit": limit,
            "offset": offset,
            "schools": [SchoolResponse.model_validate(s).model_dump() for s in schools],
        }
    )


@router.get("/{dise_code}", response_model=dict, summary="School detail")
def get_school(
    dise_code: str,
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """Fetch full details of a school by DISE code."""
    school = db.query(School).filter(School.dise_code == dise_code).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return _success(SchoolResponse.model_validate(school).model_dump())


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED, summary="Create school (admin)")
def create_school(
    payload: SchoolCreate,
    db: Session = Depends(get_db),
    _admin: Teacher = Depends(get_admin_teacher),
):
    """
    Register a new Karnataka school in the system.

    **Requires admin privileges.**
    """
    existing = db.query(School).filter(School.dise_code == payload.dise_code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"School with DISE code {payload.dise_code} already exists",
        )

    school = School(**payload.model_dump())
    db.add(school)
    db.commit()
    db.refresh(school)
    return _success(SchoolResponse.model_validate(school).model_dump(), "School created successfully")


@router.put("/{dise_code}", response_model=dict, summary="Update school")
def update_school(
    dise_code: str,
    payload: SchoolUpdate,
    db: Session = Depends(get_db),
    _admin: Teacher = Depends(get_admin_teacher),
):
    """
    Update details of an existing school.

    **Requires admin privileges.**
    """
    school = db.query(School).filter(School.dise_code == dise_code).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(school, field, value)

    db.commit()
    db.refresh(school)
    return _success(SchoolResponse.model_validate(school).model_dump(), "School updated successfully")
