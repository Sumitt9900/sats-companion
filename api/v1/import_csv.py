"""
api/v1/import_csv.py — Bulk CSV import endpoints for students and attendance.

Allows school administrative staff to import student rosters and attendance
records via CSV files. Designed for low-technical-literacy users with clear
per-row error messages and a summary report.

CSV Formats:
  Student CSV columns:
    sats_id, name, dob (DD-MM-YYYY), gender (male/female/other),
    current_class, section, school_dise_code, caste_category
    (general/obc/sc/st), father_name, mother_name, guardian_phone,
    address, aadhaar (optional)

  Attendance CSV columns:
    sats_id, attendance_date (DD-MM-YYYY), status
    (present/absent/holiday/half_day), remarks (optional)
"""
import csv
import io
import uuid
from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from core.databsae import get_db
from core.security import get_current_teacher
from core.models import Student, Attendance, Gender, CasteCategory, AttendanceStatus
from core.encryption import encrypt_field

router = APIRouter(prefix="/import", tags=["CSV Import"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(date_str: str, field_name: str, row_num: int) -> date:
    """Parse DD-MM-YYYY date string; raises ValueError with context on failure."""
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(
        f"Row {row_num}: Invalid date '{date_str}' for field '{field_name}'. "
        f"Expected format: DD-MM-YYYY"
    )


def _parse_enum(value: str, enum_cls, field_name: str, row_num: int):
    """Parse an enum value case-insensitively; raises ValueError with context."""
    value_lower = value.strip().lower()
    valid_values = [e.value for e in enum_cls]
    for enum_member in enum_cls:
        if enum_member.value == value_lower:
            return enum_member
    raise ValueError(
        f"Row {row_num}: Invalid value '{value}' for field '{field_name}'. "
        f"Valid values: {', '.join(valid_values)}"
    )


# ---------------------------------------------------------------------------
# Student CSV import
# ---------------------------------------------------------------------------

STUDENT_REQUIRED_COLUMNS = {
    "sats_id", "name", "gender", "current_class", "school_dise_code", "caste_category"
}


@router.post(
    "/students/csv",
    summary="Bulk import students from CSV",
    description=(
        "Upload a CSV file to enroll multiple students at once. "
        "Required columns: sats_id, name, gender, current_class, school_dise_code, caste_category. "
        "Optional: dob (DD-MM-YYYY), section, father_name, mother_name, guardian_phone, address, aadhaar. "
        "Returns a per-row result summary."
    ),
)
async def import_students_csv(
    file: UploadFile = File(..., description="CSV file with student records"),
    dry_run: bool = False,
    db: Session = Depends(get_db),
    teacher=Depends(get_current_teacher),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only .csv files are accepted",
        )

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV file is empty or missing headers",
        )
    missing_cols = STUDENT_REQUIRED_COLUMNS - set(f.strip() for f in reader.fieldnames)
    if missing_cols:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing required CSV columns: {', '.join(sorted(missing_cols))}",
        )

    created = 0
    skipped = 0
    failed = 0
    errors: List[dict] = []

    for row_num, row in enumerate(reader, start=2):
        row = {k.strip(): (v.strip() if v else "") for k, v in row.items()}
        sats_id = row.get("sats_id", "").strip()

        if not sats_id:
            errors.append({"row": row_num, "sats_id": None, "error": "sats_id is required"})
            failed += 1
            continue

        try:
            existing = db.query(Student).filter(Student.sats_id == sats_id).first()
            if existing:
                skipped += 1
                continue

            dob_str = row.get("dob", "")
            dob = _parse_date(dob_str, "dob", row_num) if dob_str else None

            gender = _parse_enum(row.get("gender", ""), Gender, "gender", row_num)
            caste_category = _parse_enum(
                row.get("caste_category", "general"), CasteCategory, "caste_category", row_num
            )

            aadhaar_raw = row.get("aadhaar", "") or None
            aadhaar_encrypted = encrypt_field(aadhaar_raw) if aadhaar_raw else None

            guardian_phone_raw = row.get("guardian_phone", "") or None
            guardian_phone_encrypted = encrypt_field(guardian_phone_raw) if guardian_phone_raw else None

            if not dry_run:
                student = Student(
                    sats_id=sats_id,
                    name=row.get("name", "").strip(),
                    dob=dob,
                    gender=gender,
                    current_class=row.get("current_class", "").strip(),
                    section=row.get("section", "").strip() or None,
                    school_dise_code=row.get("school_dise_code", "").strip(),
                    caste_category=caste_category,
                    father_name=row.get("father_name", "").strip() or None,
                    mother_name=row.get("mother_name", "").strip() or None,
                    guardian_name=row.get("guardian_name", "").strip() or None,
                    guardian_phone=guardian_phone_encrypted,
                    address=row.get("address", "").strip() or None,
                    aadhaar=aadhaar_encrypted,
                    is_active=True,
                )
                db.add(student)
            created += 1

        except ValueError as exc:
            errors.append({"row": row_num, "sats_id": sats_id, "error": str(exc)})
            failed += 1
        except Exception as exc:
            errors.append({
                "row": row_num,
                "sats_id": sats_id,
                "error": f"Unexpected error: {str(exc)}"
            })
            failed += 1

    if not dry_run and created > 0:
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database commit failed: {str(exc)}",
            )

    summary_msg = (
        f"{'[DRY RUN] ' if dry_run else ''}"
        f"{created} students {'would be ' if dry_run else ''}enrolled, "
        f"{skipped} duplicates skipped, {failed} rows failed."
    )

    return {
        "status": "success" if failed == 0 else "partial",
        "message": summary_msg,
        "data": {
            "created": created,
            "skipped_duplicates": skipped,
            "failed": failed,
            "total_rows_processed": created + skipped + failed,
            "dry_run": dry_run,
            "errors": errors,
        },
    }


# ---------------------------------------------------------------------------
# Attendance CSV import
# ---------------------------------------------------------------------------

ATTENDANCE_REQUIRED_COLUMNS = {"sats_id", "attendance_date", "status"}


@router.post(
    "/attendance/csv",
    summary="Bulk import attendance from CSV",
    description=(
        "Upload a CSV file to mark attendance for multiple students. "
        "Required columns: sats_id, attendance_date (DD-MM-YYYY), status (present/absent/holiday/half_day). "
        "Optional: remarks. Existing records on the same date are updated."
    ),
)
async def import_attendance_csv(
    file: UploadFile = File(..., description="CSV file with attendance records"),
    dry_run: bool = False,
    db: Session = Depends(get_db),
    teacher=Depends(get_current_teacher),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only .csv files are accepted",
        )

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV file is empty or missing headers",
        )
    missing_cols = ATTENDANCE_REQUIRED_COLUMNS - set(f.strip() for f in reader.fieldnames)
    if missing_cols:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing required CSV columns: {', '.join(sorted(missing_cols))}",
        )

    created = 0
    updated = 0
    failed = 0
    errors: List[dict] = []

    for row_num, row in enumerate(reader, start=2):
        row = {k.strip(): (v.strip() if v else "") for k, v in row.items()}
        sats_id = row.get("sats_id", "").strip()

        if not sats_id:
            errors.append({"row": row_num, "error": "sats_id is required"})
            failed += 1
            continue

        try:
            att_date = _parse_date(row.get("attendance_date", ""), "attendance_date", row_num)
            att_status = _parse_enum(row.get("status", ""), AttendanceStatus, "status", row_num)
            remarks = row.get("remarks", "").strip() or None

            student = db.query(Student).filter(Student.sats_id == sats_id).first()
            if not student:
                raise ValueError(f"Row {row_num}: Student with SATS ID '{sats_id}' not found in database")

            if not dry_run:
                existing = (
                    db.query(Attendance)
                    .filter(
                        Attendance.student_sats_id == sats_id,
                        Attendance.attendance_date == att_date,
                    )
                    .first()
                )
                if existing:
                    existing.status = att_status
                    existing.remarks = remarks
                    existing.marked_by_teacher_id = teacher.id
                    updated += 1
                else:
                    att = Attendance(
                        id=str(uuid.uuid4()),
                        student_sats_id=sats_id,
                        attendance_date=att_date,
                        status=att_status,
                        marked_by_teacher_id=teacher.id,
                        remarks=remarks,
                    )
                    db.add(att)
                    created += 1
            else:
                created += 1

        except ValueError as exc:
            errors.append({"row": row_num, "sats_id": sats_id, "error": str(exc)})
            failed += 1
        except Exception as exc:
            errors.append({
                "row": row_num,
                "sats_id": sats_id,
                "error": f"Unexpected error: {str(exc)}",
            })
            failed += 1

    if not dry_run and (created + updated) > 0:
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database commit failed: {str(exc)}",
            )

    summary_msg = (
        f"{'[DRY RUN] ' if dry_run else ''}"
        f"{created} records {'would be ' if dry_run else ''}created, "
        f"{updated} updated, {failed} rows failed."
    )

    return {
        "status": "success" if failed == 0 else "partial",
        "message": summary_msg,
        "data": {
            "created": created,
            "updated": updated,
            "failed": failed,
            "total_rows_processed": created + updated + failed,
            "dry_run": dry_run,
            "errors": errors,
        },
    }


@router.get(
    "/templates/student",
    summary="Download student import CSV template",
    description="Returns a sample CSV template with all columns for student import.",
)
def student_csv_template():
    from fastapi.responses import PlainTextResponse
    sample = (
        "sats_id,name,dob,gender,current_class,section,school_dise_code,"
        "caste_category,father_name,mother_name,guardian_phone,address,aadhaar\n"
        "SATS1001,Anand Gowda,15-06-2012,male,8,A,29010101001,"
        "obc,Manjunath Gowda,Sharada,9845012345,\"Hosahalli, Mandya\",\n"
        "SATS1002,Deepa Patil,22-03-2013,female,7,B,29010101001,"
        "general,Basavaraj Patil,Kavitha,9845054321,\"Main Road, Dharwad\",\n"
    )
    return PlainTextResponse(
        content=sample,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sats_student_import_template.csv"},
    )


@router.get(
    "/templates/attendance",
    summary="Download attendance import CSV template",
    description="Returns a sample CSV template for attendance import.",
)
def attendance_csv_template():
    from fastapi.responses import PlainTextResponse
    sample = (
        "sats_id,attendance_date,status,remarks\n"
        "SATS1001,29-10-2026,present,\n"
        "SATS1002,29-10-2026,absent,Medical leave\n"
    )
    return PlainTextResponse(
        content=sample,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sats_attendance_import_template.csv"},
    )
