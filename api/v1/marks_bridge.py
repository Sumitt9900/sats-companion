"""
api/v1/marks_bridge.py — Universal SATS Marks Bridge Endpoints with RBAC.

Enables Karnataka Teachers to ingest marks from any format (Excel, CSV, PDF, or Photo snapshot)
and submit to the Headmaster for review. Headmasters can review, verify, batch-approve & push directly
to SATS / Nirantara, or export the official Karnataka SATS CCE CSV bulk upload format.
"""

import json
from typing import List, Optional
from datetime import date, datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.databsae import get_db
from core.models import (
    Assessment, Student, Teacher, SyncOperation,
    MarksBatchSubmission, SubmissionStatus, UserRole
)
from core.rbac import require_headmaster_or_admin
from core.security import get_current_teacher
from services.marks_bridge_service import (
    generate_sats_bulk_upload_csv,
    parse_csv_marks,
    parse_excel_marks,
    parse_image_with_gemini,
    parse_pdf_marks,
)
from services.sync_service import enqueue_mutation

router = APIRouter(prefix="/marks-bridge", tags=["SATS Marks Bridge"])


def _success(data, message: str = "OK") -> dict:
    return {"status": "success", "message": message, "data": data}


class BatchAssessmentItem(BaseModel):
    student_sats_id: str
    student_name: Optional[str] = None
    current_class: Optional[str] = "8"
    subject: str
    assessment_type: str
    marks_obtained: float
    max_marks: float = 20.0
    assessment_date: Optional[date] = None
    academic_year: Optional[str] = "2026-27"


class BatchCommitRequest(BaseModel):
    records: List[BatchAssessmentItem]
    school_dise_code: Optional[str] = None


class SubmitMarksRequest(BaseModel):
    records: List[BatchAssessmentItem]
    subject: str = "Mathematics"
    assessment_type: str = "FA1"
    target_class: Optional[str] = "8"
    section: Optional[str] = "A"
    max_marks: float = 20.0
    academic_year: Optional[str] = "2026-27"
    source_filename: Optional[str] = None
    submission_notes: Optional[str] = None


class ReviewSubmissionRequest(BaseModel):
    review_notes: Optional[str] = None


@router.post("/parse", summary="Parse marks from Excel, CSV, PDF or Photo")
async def parse_marks_file(
    file: UploadFile = File(...),
    subject: str = Form("Mathematics"),
    assessment_type: str = Form("FA1"),
    max_marks: float = Form(20.0),
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Parse student marks from an arbitrary teacher file:
    - Excel (.xlsx, .xls)
    - CSV (.csv)
    - PDF score sheet (.pdf)
    - Photo of notebook/register (.jpg, .jpeg, .png, .webp)
    """
    filename = (file.filename or "").lower()
    contents = await file.read()

    # Get active enrolled students for school roster matching
    students = (
        db.query(Student)
        .filter(Student.school_dise_code == teacher.school_dise_code, Student.is_active == True)
        .all()
    )
    roster = [{"sats_id": s.sats_id, "name": s.name, "current_class": s.current_class} for s in students]

    records = []
    parser_used = ""

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            records = parse_excel_marks(contents, roster, subject, assessment_type, max_marks)
            parser_used = "Excel Spreadsheet Parser"
        elif filename.endswith(".csv"):
            records = parse_csv_marks(contents, roster, subject, assessment_type, max_marks)
            parser_used = "CSV Parser"
        elif filename.endswith(".pdf"):
            records = parse_pdf_marks(contents, roster, subject, assessment_type, max_marks)
            parser_used = "PDF Text Extraction Parser"
        elif any(filename.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            mime_type = file.content_type or "image/jpeg"
            records = parse_image_with_gemini(contents, mime_type, roster, subject, assessment_type, max_marks)
            parser_used = "Gemini 2.0 Multimodal Vision OCR"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported format. Please upload an Excel (.xlsx), CSV, PDF, or Photo (.jpg/.png).",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Parsing error: {str(e)}",
        )

    matched = sum(1 for r in records if r.get("match_status") in ("exact", "name_match"))
    unmatched = len(records) - matched

    return _success(
        {
            "records": records,
            "total": len(records),
            "matched": matched,
            "unmatched": unmatched,
            "parser_used": parser_used,
            "school_dise": teacher.school_dise_code,
        },
        f"Successfully extracted {len(records)} candidate mark records ({matched} matched to school roster).",
    )


@router.post("/submit", summary="Teacher submits ingested marks for Headmaster approval")
def submit_marks_batch(
    payload: SubmitMarksRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Submits ingested & verified marks to the Headmaster for review and SATS upload.
    Teachers can upload register photos or Excel sheets and queue them for the HM.
    """
    if not payload.records:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No marks records provided")

    # Serialize records as JSON
    records_data = [r.model_dump(mode="json") for r in payload.records]

    submission = MarksBatchSubmission(
        school_dise_code=teacher.school_dise_code or "29210101001",
        submitted_by_teacher_id=teacher.id,
        academic_year=payload.academic_year or "2026-27",
        target_class=payload.target_class or "8",
        section=payload.section or "A",
        subject=payload.subject,
        assessment_type=payload.assessment_type,
        max_marks=payload.max_marks,
        total_records=len(payload.records),
        source_filename=payload.source_filename,
        records_json=json.dumps(records_data),
        status=SubmissionStatus.PENDING_APPROVAL,
        submission_notes=payload.submission_notes,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    return _success(
        {
            "submission_id": submission.id,
            "status": submission.status.value,
            "total_records": submission.total_records,
            "subject": submission.subject,
            "assessment_type": submission.assessment_type,
            "created_at": submission.created_at.isoformat() if submission.created_at else None,
        },
        f"Submitted {submission.total_records} marks to Headmaster for review & SATS upload.",
    )


@router.get("/submissions", summary="List marks submissions for review or status tracking")
def list_submissions(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    List marks submissions.
    - Headmasters / Admins see all submissions across the school.
    - Teachers see their own submissions and approval status.
    """
    query = db.query(MarksBatchSubmission)
    is_hm = (teacher.role == UserRole.HEADMASTER or teacher.is_admin)

    if is_hm:
        query = query.filter(MarksBatchSubmission.school_dise_code == teacher.school_dise_code)
    else:
        query = query.filter(MarksBatchSubmission.submitted_by_teacher_id == teacher.id)

    if status_filter:
        try:
            status_enum = SubmissionStatus(status_filter.lower())
            query = query.filter(MarksBatchSubmission.status == status_enum)
        except ValueError:
            pass

    submissions = query.order_by(MarksBatchSubmission.created_at.desc()).all()

    results = []
    for s in submissions:
        submitter_name = s.submitted_by.name if s.submitted_by else "Teacher"
        submitter_kgid = s.submitted_by.kgid if s.submitted_by else ""
        reviewer_name = s.reviewed_by.name if s.reviewed_by else None

        results.append({
            "id": s.id,
            "school_dise_code": s.school_dise_code,
            "submitted_by_teacher_id": s.submitted_by_teacher_id,
            "submitted_by_name": submitter_name,
            "submitted_by_kgid": submitter_kgid,
            "reviewer_name": reviewer_name,
            "academic_year": s.academic_year,
            "target_class": s.target_class,
            "section": s.section,
            "subject": s.subject,
            "assessment_type": s.assessment_type,
            "max_marks": s.max_marks,
            "total_records": s.total_records,
            "source_filename": s.source_filename,
            "status": s.status.value,
            "submission_notes": s.submission_notes,
            "hm_review_notes": s.hm_review_notes,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
        })

    pending_count = sum(1 for r in results if r["status"] == "pending_approval")

    return _success(
        {
            "submissions": results,
            "total": len(results),
            "pending_count": pending_count,
            "is_headmaster": is_hm,
        },
        f"Retrieved {len(results)} submission(s).",
    )


@router.get("/submissions/{submission_id}", summary="Get submission details and candidate marks records")
def get_submission_detail(
    submission_id: str,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Get full submission details including all candidate records for HM review or teacher viewing.
    """
    sub = db.query(MarksBatchSubmission).filter(MarksBatchSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    is_hm = (teacher.role == UserRole.HEADMASTER or teacher.is_admin)
    if not is_hm and sub.submitted_by_teacher_id != teacher.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this submission")

    records = []
    try:
        records = json.loads(sub.records_json)
    except Exception:
        records = []

    return _success({
        "id": sub.id,
        "school_dise_code": sub.school_dise_code,
        "submitted_by_name": sub.submitted_by.name if sub.submitted_by else "Teacher",
        "submitted_by_kgid": sub.submitted_by.kgid if sub.submitted_by else "",
        "academic_year": sub.academic_year,
        "target_class": sub.target_class,
        "section": sub.section,
        "subject": sub.subject,
        "assessment_type": sub.assessment_type,
        "max_marks": sub.max_marks,
        "total_records": sub.total_records,
        "source_filename": sub.source_filename,
        "status": sub.status.value,
        "submission_notes": sub.submission_notes,
        "hm_review_notes": sub.hm_review_notes,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
        "reviewed_at": sub.reviewed_at.isoformat() if sub.reviewed_at else None,
        "records": records,
    })


@router.post("/submissions/{submission_id}/approve", summary="Headmaster approves and commits marks directly to SATS")
def approve_submission(
    submission_id: str,
    payload: Optional[ReviewSubmissionRequest] = None,
    db: Session = Depends(get_db),
    headmaster: Teacher = Depends(require_headmaster_or_admin),
):
    """
    RBAC: Headmaster or Admin only.
    Approves the teacher's submission, writes all marks to the database,
    and enqueues the mutation to the central SATS synchronization queue.
    """
    sub = db.query(MarksBatchSubmission).filter(MarksBatchSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    if sub.school_dise_code != headmaster.school_dise_code and not headmaster.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot approve submissions from another school")

    try:
        records_data = json.loads(sub.records_json)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Corrupted records in submission: {str(e)}")

    today = date.today()
    saved_count = 0
    updated_count = 0

    for item in records_data:
        sats_id = item.get("student_sats_id")
        if not sats_id:
            continue
        student = db.query(Student).filter(Student.sats_id == sats_id).first()
        if not student:
            continue

        subj = item.get("subject") or sub.subject
        ass_type = item.get("assessment_type") or sub.assessment_type
        acad_yr = item.get("academic_year") or sub.academic_year or "2026-27"
        marks_obt = float(item.get("marks_obtained", 0.0))
        max_m = float(item.get("max_marks", sub.max_marks))

        existing = (
            db.query(Assessment)
            .filter(
                Assessment.student_sats_id == sats_id,
                Assessment.subject == subj,
                Assessment.assessment_type == ass_type,
                Assessment.academic_year == acad_yr,
            )
            .first()
        )

        if existing:
            existing.marks_obtained = marks_obt
            existing.max_marks = max_m
            existing.assessment_date = today
            updated_count += 1
        else:
            new_assessment = Assessment(
                student_sats_id=sats_id,
                subject=subj,
                assessment_type=ass_type,
                marks_obtained=marks_obt,
                max_marks=max_m,
                assessment_date=today,
                academic_year=acad_yr,
                recorded_by_teacher_id=sub.submitted_by_teacher_id,
            )
            db.add(new_assessment)
            saved_count += 1

    sub.status = SubmissionStatus.APPROVED
    sub.reviewed_by_teacher_id = headmaster.id
    sub.reviewed_at = datetime.utcnow()
    if payload and payload.review_notes:
        sub.hm_review_notes = payload.review_notes

    db.commit()

    # Enqueue mutation to sync queue
    enqueue_mutation(
        db=db,
        operation=SyncOperation.CREATE,
        entity_type="assessment_batch",
        entity_id=f"submission_{sub.id}",
        payload={
            "submission_id": sub.id,
            "school_dise": headmaster.school_dise_code,
            "subject": sub.subject,
            "assessment_type": sub.assessment_type,
            "total_marks_records": saved_count + updated_count,
            "approved_by_kgid": headmaster.kgid,
            "date": today.isoformat(),
        },
    )

    return _success(
        {
            "submission_id": sub.id,
            "status": sub.status.value,
            "created": saved_count,
            "updated": updated_count,
            "total": saved_count + updated_count,
        },
        f"Approved! Committed {saved_count + updated_count} marks to SATS ({saved_count} new, {updated_count} updated) and queued for sync.",
    )


@router.post("/submissions/{submission_id}/reject", summary="Headmaster rejects submission with feedback for teacher revision")
def reject_submission(
    submission_id: str,
    payload: Optional[ReviewSubmissionRequest] = None,
    db: Session = Depends(get_db),
    headmaster: Teacher = Depends(require_headmaster_or_admin),
):
    """
    RBAC: Headmaster or Admin only.
    Rejects the submission and provides feedback for the teacher to revise.
    """
    sub = db.query(MarksBatchSubmission).filter(MarksBatchSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    sub.status = SubmissionStatus.REJECTED
    sub.reviewed_by_teacher_id = headmaster.id
    sub.reviewed_at = datetime.utcnow()
    if payload and payload.review_notes:
        sub.hm_review_notes = payload.review_notes

    db.commit()

    return _success(
        {"submission_id": sub.id, "status": sub.status.value},
        "Submission marked as rejected and sent back to teacher for revision.",
    )


@router.get("/submissions/{submission_id}/export-sats-csv", summary="Export official Karnataka SATS CCE CSV for submission")
def export_submission_sats_csv(
    submission_id: str,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Export the submission's records directly in official Karnataka SATS CCE bulk-upload format.
    """
    sub = db.query(MarksBatchSubmission).filter(MarksBatchSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    try:
        records_data = json.loads(sub.records_json)
    except Exception:
        records_data = []

    csv_text = generate_sats_bulk_upload_csv(
        records=records_data,
        school_dise_code=sub.school_dise_code,
    )

    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=sats_cce_{sub.subject}_{sub.assessment_type}_{sub.school_dise_code}.csv"
        },
    )


@router.post("/batch-commit", summary="Direct commit verified marks to database and SATS queue")
def batch_commit_marks(
    payload: BatchCommitRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Commit reviewed and verified marks into the school's local database and
    appends mutations to the SATS synchronization queue.
    """
    if not payload.records:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No records provided")

    saved_count = 0
    updated_count = 0
    today = date.today()

    for item in payload.records:
        student = db.query(Student).filter(Student.sats_id == item.student_sats_id).first()
        if not student:
            continue

        existing = (
            db.query(Assessment)
            .filter(
                Assessment.student_sats_id == item.student_sats_id,
                Assessment.subject == item.subject,
                Assessment.assessment_type == item.assessment_type,
                Assessment.academic_year == (item.academic_year or "2026-27"),
            )
            .first()
        )

        if existing:
            existing.marks_obtained = item.marks_obtained
            existing.max_marks = item.max_marks
            existing.assessment_date = item.assessment_date or today
            updated_count += 1
        else:
            new_assessment = Assessment(
                student_sats_id=item.student_sats_id,
                subject=item.subject,
                assessment_type=item.assessment_type,
                marks_obtained=item.marks_obtained,
                max_marks=item.max_marks,
                assessment_date=item.assessment_date or today,
                academic_year=item.academic_year or "2026-27",
                recorded_by_teacher_id=teacher.id,
            )
            db.add(new_assessment)
            saved_count += 1

    db.commit()

    # Queue sync mutation
    enqueue_mutation(
        db=db,
        operation=SyncOperation.CREATE,
        entity_type="assessment_batch",
        entity_id=f"batch_{today.isoformat()}_{saved_count + updated_count}",
        payload={
            "school_dise": teacher.school_dise_code,
            "total_marks_records": saved_count + updated_count,
            "date": today.isoformat(),
        },
    )

    return _success(
        {
            "created": saved_count,
            "updated": updated_count,
            "total": saved_count + updated_count,
        },
        f"Committed {saved_count + updated_count} marks to SATS records ({saved_count} new, {updated_count} updated).",
    )


@router.post("/export-sats-format", summary="Generate official Karnataka SATS CCE CSV upload file")
def export_sats_format(
    payload: BatchCommitRequest,
    teacher: Teacher = Depends(get_current_teacher),
):
    """
    Export marks records as the official SATS bulk upload CSV accepted by sts.karnataka.gov.in.
    """
    records_dict = [r.model_dump() for r in payload.records]
    csv_text = generate_sats_bulk_upload_csv(
        records=records_dict,
        school_dise_code=payload.school_dise_code or teacher.school_dise_code,
    )

    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=sats_cce_marks_upload_{teacher.school_dise_code}.csv"
        },
    )
