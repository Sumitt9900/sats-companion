"""
services/marks_bridge_service.py — Universal SATS & Nirantara Marks Bridge Service.

Translates marks from ANY format (Excel, CSV, PDF, or Photo snapshot of paper score sheets)
into the official Karnataka SATS CCE format, eliminating manual student-by-student entry.
"""

import csv
import io
import json
import re
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from pypdf import PdfReader

from core.config import settings


# ---------------------------------------------------------------------------
# SATS CCE Standards & Subjects
# ---------------------------------------------------------------------------
STANDARD_SUBJECTS = {
    "kan": "Kannada",
    "kannada": "Kannada",
    "first language": "Kannada",
    "ಕನ್ನಡ": "Kannada",
    "eng": "English",
    "english": "English",
    "second language": "English",
    "ಇಂಗ್ಲಿಷ್": "English",
    "hin": "Hindi",
    "hindi": "Hindi",
    "third language": "Hindi",
    "ಹಿಂದಿ": "Hindi",
    "mat": "Mathematics",
    "math": "Mathematics",
    "maths": "Mathematics",
    "mathematics": "Mathematics",
    "ಗಣಿತ": "Mathematics",
    "sci": "Science",
    "science": "Science",
    "ವಿಜ್ಞಾನ": "Science",
    "soc": "Social Science",
    "social": "Social Science",
    "social science": "Social Science",
    "ಸಮಾಜ": "Social Science",
    "ಸಮಾಜ ವಿಜ್ಞಾನ": "Social Science",
}

VALID_ASSESSMENT_TYPES = ["FA1", "FA2", "SA1", "FA3", "FA4", "SA2"]


def normalize_subject_name(raw: str, default: str = "Mathematics") -> str:
    """Normalize arbitrary subject names from teacher files to SATS standard."""
    clean = raw.strip().lower()
    for key, val in STANDARD_SUBJECTS.items():
        if key in clean:
            return val
    return default


def normalize_assessment_type(raw: Optional[str], default: str = "FA1") -> str:
    """Ensure assessment type is valid SATS type."""
    if not raw:
        return default
    clean = raw.strip().upper()
    for t in VALID_ASSESSMENT_TYPES:
        if t in clean:
            return t
    return default


def calculate_cce_grade(marks: float, max_marks: float) -> str:
    """Calculate standard Karnataka CCE grade."""
    if max_marks <= 0:
        return "N/A"
    pct = (marks / max_marks) * 100
    if pct >= 90:
        return "A+"
    if pct >= 80:
        return "A"
    if pct >= 70:
        return "B+"
    if pct >= 60:
        return "B"
    if pct >= 50:
        return "C+"
    if pct >= 35:
        return "C"
    return "D"


# ---------------------------------------------------------------------------
# Student Matcher (SATS ID & Fuzzy Name Matching)
# ---------------------------------------------------------------------------
def match_student_in_roster(
    candidate_id: str,
    candidate_name: str,
    enrolled_students: List[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Match candidate data against school roster.
    Returns (matched_student_dict, match_status: 'exact' | 'name_match' | 'unmatched').
    """
    clean_id = (candidate_id or "").strip().upper()
    clean_name = (candidate_name or "").strip().lower()

    # 1. Exact SATS ID match
    if clean_id:
        for s in enrolled_students:
            if s.get("sats_id", "").upper() == clean_id:
                return s, "exact"

    # 2. Exact or substring Name match
    if clean_name:
        for s in enrolled_students:
            s_name = s.get("name", "").lower()
            if s_name == clean_name:
                return s, "name_match"
            # Overlap check
            if len(clean_name) >= 4 and (clean_name in s_name or s_name in clean_name):
                return s, "name_match"

    return None, "unmatched"


# ---------------------------------------------------------------------------
# 1. Excel Spreadsheet Parser (.xlsx, .xls)
# ---------------------------------------------------------------------------
def parse_excel_marks(
    file_bytes: bytes,
    enrolled_students: List[Dict[str, Any]],
    default_subject: str = "Mathematics",
    default_type: str = "FA1",
    default_max_marks: float = 20.0,
) -> List[Dict[str, Any]]:
    """
    Parse teacher Excel spreadsheet into SATS candidate marks records.
    Handles both Single-Subject and Multi-Subject wide formats.
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    sheet = wb.active

    rows = []
    for row in sheet.iter_rows(values_only=True):
        if any(cell is not None for cell in row):
            rows.append([str(c).strip() if c is not None else "" for c in row])

    if not rows:
        return []

    # Find header row
    header_idx = -1
    for i, row in enumerate(rows[:10]):
        row_str = " ".join(row).lower()
        if any(keyword in row_str for keyword in ["sats", "name", "student", "roll", "kannada", "math", "marks", "fa1", "sa1"]):
            header_idx = i
            break

    if header_idx == -1:
        header_idx = 0

    headers = [h.strip() for h in rows[header_idx]]
    data_rows = rows[header_idx + 1 :]

    # Detect column indexes
    sats_col = -1
    name_col = -1
    subject_cols = {}  # {col_idx: subject_name}

    for col_idx, h in enumerate(headers):
        h_lower = h.lower()
        if "sats" in h_lower or "reg" in h_lower:
            sats_col = col_idx
        elif "name" in h_lower or "student" in h_lower or "ವಿದ್ಯಾರ್ಥಿ" in h_lower:
            name_col = col_idx
        else:
            # Check if this column is a subject
            for s_key, s_val in STANDARD_SUBJECTS.items():
                if s_key in h_lower:
                    subject_cols[col_idx] = s_val
                    break

    # If no multi-subject columns found, look for general "Marks" or "Score"
    if not subject_cols:
        marks_col = -1
        for col_idx, h in enumerate(headers):
            h_lower = h.lower()
            if any(k in h_lower for k in ["mark", "score", "ಅಂಕ", "obtained"]):
                marks_col = col_idx
                break
        if marks_col == -1 and len(headers) >= 3:
            marks_col = len(headers) - 1  # Default to last column
        if marks_col != -1:
            subject_cols[marks_col] = default_subject

    results = []
    for r in data_rows:
        cand_id = r[sats_col] if sats_col != -1 and sats_col < len(r) else ""
        cand_name = r[name_col] if name_col != -1 and name_col < len(r) else ""

        matched_student, match_status = match_student_in_roster(cand_id, cand_name, enrolled_students)
        student_sats = matched_student.get("sats_id") if matched_student else cand_id
        student_display_name = matched_student.get("name") if matched_student else cand_name
        current_class = matched_student.get("current_class", "8") if matched_student else "8"

        for col_idx, subj in subject_cols.items():
            if col_idx < len(r):
                raw_val = r[col_idx].strip()
                if not raw_val or raw_val.lower() in ["na", "-", "null"]:
                    continue

                is_absent = raw_val.lower() in ["ab", "absent", "a", "ಗೈರು"]
                try:
                    marks_val = 0.0 if is_absent else float(raw_val)
                except ValueError:
                    continue

                grade = "AB" if is_absent else calculate_cce_grade(marks_val, default_max_marks)

                results.append({
                    "student_sats_id": student_sats,
                    "student_name": student_display_name,
                    "current_class": current_class,
                    "subject": subj,
                    "assessment_type": default_type,
                    "marks_obtained": marks_val,
                    "max_marks": default_max_marks,
                    "is_absent": is_absent,
                    "grade": grade,
                    "match_status": match_status,
                })

    return results


# ---------------------------------------------------------------------------
# 2. CSV Parser (.csv)
# ---------------------------------------------------------------------------
def parse_csv_marks(
    file_bytes: bytes,
    enrolled_students: List[Dict[str, Any]],
    default_subject: str = "Mathematics",
    default_type: str = "FA1",
    default_max_marks: float = 20.0,
) -> List[Dict[str, Any]]:
    """Parse comma/tab separated mark file into normalized records."""
    content = ""
    for enc in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            content = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if not content:
        return []

    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines:
        return []

    dialect = csv.Sniffer().sniff(lines[0]) if len(lines) > 1 else csv.excel
    reader = csv.reader(io.StringIO(content), dialect=dialect)
    rows = [r for r in reader if any(r)]

    if not rows:
        return []

    headers = [h.strip() for h in rows[0]]
    sats_col = -1
    name_col = -1
    subject_cols = {}

    for col_idx, h in enumerate(headers):
        h_lower = h.lower()
        if "sats" in h_lower or "id" in h_lower:
            sats_col = col_idx
        elif "name" in h_lower or "student" in h_lower or "ವಿದ್ಯಾರ್ಥಿ" in h_lower:
            name_col = col_idx
        else:
            for s_key, s_val in STANDARD_SUBJECTS.items():
                if s_key in h_lower:
                    subject_cols[col_idx] = s_val
                    break

    if not subject_cols:
        marks_col = -1
        for col_idx, h in enumerate(headers):
            if any(k in h.lower() for k in ["mark", "score", "ಅಂಕ"]):
                marks_col = col_idx
                break
        if marks_col == -1 and len(headers) >= 3:
            marks_col = len(headers) - 1
        if marks_col != -1:
            subject_cols[marks_col] = default_subject

    results = []
    for r in rows[1:]:
        cand_id = r[sats_col].strip() if sats_col != -1 and sats_col < len(r) else ""
        cand_name = r[name_col].strip() if name_col != -1 and name_col < len(r) else ""

        matched_student, match_status = match_student_in_roster(cand_id, cand_name, enrolled_students)
        student_sats = matched_student.get("sats_id") if matched_student else cand_id
        student_display_name = matched_student.get("name") if matched_student else cand_name
        current_class = matched_student.get("current_class", "8") if matched_student else "8"

        for col_idx, subj in subject_cols.items():
            if col_idx < len(r):
                raw_val = r[col_idx].strip()
                if not raw_val or raw_val.lower() in ["na", "-", "null"]:
                    continue

                is_absent = raw_val.lower() in ["ab", "absent", "a", "ಗೈರು"]
                try:
                    marks_val = 0.0 if is_absent else float(raw_val)
                except ValueError:
                    continue

                grade = "AB" if is_absent else calculate_cce_grade(marks_val, default_max_marks)

                results.append({
                    "student_sats_id": student_sats,
                    "student_name": student_display_name,
                    "current_class": current_class,
                    "subject": subj,
                    "assessment_type": default_type,
                    "marks_obtained": marks_val,
                    "max_marks": default_max_marks,
                    "is_absent": is_absent,
                    "grade": grade,
                    "match_status": match_status,
                })

    return results


# ---------------------------------------------------------------------------
# 3. PDF Marks Tabulation Parser
# ---------------------------------------------------------------------------
def parse_pdf_marks(
    file_bytes: bytes,
    enrolled_students: List[Dict[str, Any]],
    default_subject: str = "Mathematics",
    default_type: str = "FA1",
    default_max_marks: float = 20.0,
) -> List[Dict[str, Any]]:
    """Extract tabular score lines from a digital or printed PDF file."""
    reader = PdfReader(io.BytesIO(file_bytes))
    full_text = ""
    for page in reader.pages:
        full_text += (page.extract_text() or "") + "\n"

    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
    results = []

    for line in lines:
        # Check if line contains SATS ID e.g. SATS2901001 or SATSxxxx
        sats_match = re.search(r"\b(SATS\w+|\d{7,12})\b", line, re.IGNORECASE)
        # Find numeric scores (e.g. 18.5, 20, 15)
        numbers = re.findall(r"\b\d+(?:\.\d+)?\b", line)

        if sats_match and numbers:
            cand_id = sats_match.group(1).upper()
            matched_student, match_status = match_student_in_roster(cand_id, "", enrolled_students)
            score_cand = float(numbers[-1])  # Usually last number is the mark
            if score_cand <= default_max_marks:
                results.append({
                    "student_sats_id": matched_student.get("sats_id", cand_id) if matched_student else cand_id,
                    "student_name": matched_student.get("name", "Student") if matched_student else "Extracted Student",
                    "current_class": matched_student.get("current_class", "8") if matched_student else "8",
                    "subject": default_subject,
                    "assessment_type": default_type,
                    "marks_obtained": score_cand,
                    "max_marks": default_max_marks,
                    "is_absent": False,
                    "grade": calculate_cce_grade(score_cand, default_max_marks),
                    "match_status": match_status,
                })

    return results


# ---------------------------------------------------------------------------
# 4. Multimodal Photo / Score-Sheet AI Extractor (Gemini 2.0 Vision)
# ---------------------------------------------------------------------------
def parse_image_with_gemini(
    file_bytes: bytes,
    mime_type: str,
    enrolled_students: List[Dict[str, Any]],
    default_subject: str = "Mathematics",
    default_type: str = "FA1",
    default_max_marks: float = 20.0,
) -> List[Dict[str, Any]]:
    """
    Use Google Gemini 2.0 Flash to extract marks from a photo of a handwritten
    score register, student mark paper, or mobile phone camera snapshot.
    """
    if not settings.GOOGLE_API_KEY:
        raise ValueError(
            "Google GenAI API key is not configured. Please add GOOGLE_API_KEY to your environment, "
            "or upload an Excel/CSV file."
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GOOGLE_API_KEY)

    student_roster_summary = "\n".join(
        f"- SATS ID: {s.get('sats_id')}, Name: {s.get('name')}, Class: {s.get('current_class')}"
        for s in enrolled_students[:60]
    )

    prompt = f"""You are an expert OCR and data extraction system assisting a Karnataka Government School Headmaster.
Your task is to transcribe student examination marks from this marks register photo/document for the Karnataka SATS (Student Achievement Tracking System).

Target Parameters:
- Default Assessment Type: {default_type} (e.g. FA1, FA2, SA1)
- Default Subject: {default_subject}
- Default Max Marks: {default_max_marks}

Enrolled School Students for Reference (match these names/IDs if visible):
{student_roster_summary}

Instructions:
1. Examine each student row carefully (handwritten or printed).
2. Read the Student Name, Roll No or SATS ID, and the Marks obtained.
3. If multiple subjects are shown (e.g. Kan, Eng, Math, Sci, Soc), extract each subject entry separately.
4. Mark absent students with is_absent: true and marks_obtained: 0.
5. Return ONLY a valid JSON array of objects with these exact keys:
[
  {{
    "student_sats_id": "SATS ID or best guess from roster",
    "student_name": "Student name",
    "subject": "Subject name (e.g. Mathematics, Science, Social Science, Kannada, English, Hindi)",
    "assessment_type": "{default_type}",
    "marks_obtained": 18.5,
    "max_marks": {default_max_marks},
    "is_absent": false
  }}
]
Do not include markdown code block wrappers (like ```json), just output the raw JSON array.
"""

    contents = [
        types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
        prompt,
    ]

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=contents,
    )

    text_resp = (response.text or "").strip()
    text_resp = re.sub(r"^```json\s*", "", text_resp)
    text_resp = re.sub(r"\s*```$", "", text_resp)

    try:
        raw_list = json.loads(text_resp)
    except Exception as e:
        raise ValueError(f"Could not parse AI response as JSON: {e}\nResponse: {text_resp[:200]}")

    results = []
    for item in raw_list:
        cand_id = item.get("student_sats_id", "")
        cand_name = item.get("student_name", "")
        matched_student, match_status = match_student_in_roster(cand_id, cand_name, enrolled_students)

        student_sats = matched_student.get("sats_id") if matched_student else cand_id
        student_display_name = matched_student.get("name") if matched_student else cand_name
        current_class = matched_student.get("current_class", "8") if matched_student else "8"

        subj = normalize_subject_name(item.get("subject", default_subject), default_subject)
        marks_val = float(item.get("marks_obtained", 0.0))
        max_m = float(item.get("max_marks", default_max_marks))
        is_absent = bool(item.get("is_absent", False))

        results.append({
            "student_sats_id": student_sats,
            "student_name": student_display_name,
            "current_class": current_class,
            "subject": subj,
            "assessment_type": normalize_assessment_type(item.get("assessment_type"), default_type),
            "marks_obtained": 0.0 if is_absent else marks_val,
            "max_marks": max_m,
            "is_absent": is_absent,
            "grade": "AB" if is_absent else calculate_cce_grade(marks_val, max_m),
            "match_status": match_status,
        })

    return results


# ---------------------------------------------------------------------------
# 5. SATS Official Bulk Upload CSV Generator
# ---------------------------------------------------------------------------
def generate_sats_bulk_upload_csv(
    records: List[Dict[str, Any]],
    school_dise_code: str = "29210101001",
    academic_year: str = "2026-27",
) -> str:
    """
    Format validated marks into the exact official Karnataka SATS / Nirantara
    bulk CSV upload format for one-click upload to sts.karnataka.gov.in.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Official SATS CCE format headers
    headers = [
        "Academic_Year",
        "School_DISE",
        "Class",
        "Section",
        "SATS_ID",
        "Student_Name",
        "Assessment_Type",
        "Subject",
        "Max_Marks",
        "Marks_Obtained",
        "Grade",
        "Attendance_Status",
    ]
    writer.writerow(headers)

    for r in records:
        writer.writerow([
            academic_year,
            school_dise_code,
            r.get("current_class", "8"),
            r.get("section", "A"),
            r.get("student_sats_id", ""),
            r.get("student_name", ""),
            r.get("assessment_type", "FA1"),
            r.get("subject", "Mathematics"),
            r.get("max_marks", 20.0),
            r.get("marks_obtained", 0.0),
            r.get("grade", "N/A"),
            "ABSENT" if r.get("is_absent") else "PRESENT",
        ])

    return output.getvalue()
