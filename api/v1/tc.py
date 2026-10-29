"""
api/v1/tc.py — Transfer Certificate (TC) management endpoints.

POST /api/v1/tc/request              — Request TC for a student
GET  /api/v1/tc/{tc_id}              — Get TC details
PUT  /api/v1/tc/{tc_id}/approve      — Approve / reject TC (admin/HM)
GET  /api/v1/tc/student/{sats_id}    — TC history for a student
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.databsae import get_db
from core.models import TransferCertificate, Student, Teacher, TCStatus
from core.security import get_current_teacher, get_admin_teacher
from schemas.tc import TCRequest, TCApproval, TCResponse

router = APIRouter(prefix="/tc", tags=["Transfer Certificates"])


def _success(data, message: str = "OK") -> dict:
    return {"status": "success", "message": message, "data": data}


@router.post("/request", response_model=dict, status_code=status.HTTP_201_CREATED, summary="Request TC")
def request_tc(
    payload: TCRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Initiate a Transfer Certificate request for a student.

    The TC moves through: REQUESTED → UNDER_REVIEW → APPROVED → ISSUED.
    Only approved TCs can be issued to students / receiving schools.
    """
    student = db.query(Student).filter(
        Student.sats_id == payload.student_sats_id,
        Student.is_active == True,
    ).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found or inactive")

    # Check for pending TC
    pending = db.query(TransferCertificate).filter(
        TransferCertificate.student_sats_id == payload.student_sats_id,
        TransferCertificate.status.in_([TCStatus.REQUESTED, TCStatus.UNDER_REVIEW]),
    ).first()
    if pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An active TC request (ID: {pending.id}) already exists for this student",
        )

    tc = TransferCertificate(
        student_sats_id=payload.student_sats_id,
        issuing_school_dise=payload.issuing_school_dise,
        receiving_school_dise=payload.receiving_school_dise,
        reason=payload.reason,
        request_date=payload.request_date or date.today(),
        requested_by_teacher_id=teacher.id,
        status=TCStatus.REQUESTED,
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return _success(TCResponse.model_validate(tc).model_dump(), "TC request submitted successfully")


@router.get("/student/{sats_id}", response_model=dict, summary="TC history for student")
def get_student_tcs(
    sats_id: str,
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """Return all TC records for a student, ordered by most recent first."""
    student = db.query(Student).filter(Student.sats_id == sats_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    tcs = (
        db.query(TransferCertificate)
        .filter(TransferCertificate.student_sats_id == sats_id)
        .order_by(TransferCertificate.created_at.desc())
        .all()
    )
    return _success(
        {
            "student": {"sats_id": student.sats_id, "name": student.name},
            "tc_count": len(tcs),
            "transfer_certificates": [TCResponse.model_validate(tc).model_dump() for tc in tcs],
        }
    )


@router.get("/{tc_id}", response_model=dict, summary="TC detail")
def get_tc(
    tc_id: str,
    db: Session = Depends(get_db),
    _teacher: Teacher = Depends(get_current_teacher),
):
    """Fetch full details of a Transfer Certificate by its ID."""
    tc = db.query(TransferCertificate).filter(TransferCertificate.id == tc_id).first()
    if not tc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TC not found")
    return _success(TCResponse.model_validate(tc).model_dump())


@router.put("/{tc_id}/approve", response_model=dict, summary="Approve or reject TC")
def approve_tc(
    tc_id: str,
    payload: TCApproval,
    db: Session = Depends(get_db),
    admin: Teacher = Depends(get_admin_teacher),
):
    """
    Approve, reject, or issue a Transfer Certificate.

    **Requires admin / Headmaster privileges.**

    Valid status transitions:
    - REQUESTED → UNDER_REVIEW / APPROVED / REJECTED
    - UNDER_REVIEW → APPROVED / REJECTED
    - APPROVED → ISSUED
    """
    tc = db.query(TransferCertificate).filter(TransferCertificate.id == tc_id).first()
    if not tc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TC not found")

    if tc.status == TCStatus.ISSUED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="TC has already been issued and cannot be modified",
        )
    if tc.status == TCStatus.REJECTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="TC has been rejected; submit a new TC request if needed",
        )

    tc.status = payload.status
    tc.approved_by_teacher_id = admin.id
    tc.remarks = payload.remarks or tc.remarks

    if payload.status in (TCStatus.APPROVED, TCStatus.ISSUED):
        tc.approval_date = payload.issue_date or date.today()
        if payload.tc_number:
            tc.tc_number = payload.tc_number
        if payload.status == TCStatus.ISSUED:
            tc.issue_date = payload.issue_date or date.today()
            # Mark student as transferred
            student = db.query(Student).filter(Student.sats_id == tc.student_sats_id).first()
            if student:
                student.is_transferred = True
                student.is_active = False

    db.commit()
    db.refresh(tc)
    return _success(TCResponse.model_validate(tc).model_dump(), f"TC status updated to {payload.status.value}")
