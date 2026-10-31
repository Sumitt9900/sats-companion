"""
api/v1/marks_bridge.py — Universal SATS Marks Bridge Endpoints.

Enables Karnataka Headmasters and Teachers to ingest marks from any format
(Excel, CSV, PDF, or Photo snapshot of paper marks register) and batch-commit
or export directly in official Karnataka SATS / Nirantara format.
"""

from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.databsae import get_db
from core.models import Assessment, Student, Teacher, SyncOperation
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


@router.post("/batch-commit", summary="Commit verified marks to database and SATS queue")
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
        # Verify student exists
        student = db.query(Student).filter(Student.sats_id == item.student_sats_id).first()
        if not student:
            continue

        # Check for existing assessment to update or create
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
