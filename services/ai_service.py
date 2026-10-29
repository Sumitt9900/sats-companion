"""
services/ai_service.py — Google Gemini AI integration for SATS Companion.

All AI prompts are Karnataka-context aware, referencing:
  - Karnataka SATS system, KGID teacher IDs
  - Kannada-medium and English-medium schools
  - Karnataka state curriculum (KSEEB / NEP 2020)
  - Karnataka districts and school types
"""
from typing import Optional
from google import genai

from core.config import settings

# ---------------------------------------------------------------------------
# Gemini client (google-genai 0.3.0 API)
# ---------------------------------------------------------------------------
_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    """Lazily initialise and return the Gemini client singleton."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _client


def _generate(prompt: str, model: str = "gemini-2.0-flash") -> str:
    """
    Send *prompt* to Gemini and return the text response.

    Args:
        prompt: Full prompt string.
        model: Gemini model identifier.

    Returns:
        Generated text from the model.

    Raises:
        RuntimeError: If the API call fails.
    """
    client = _get_client()
    response = client.models.generate_content(
        model=model,
        contents=prompt,
    )
    return response.text


# ---------------------------------------------------------------------------
# AI service functions
# ---------------------------------------------------------------------------

def generate_student_report(student_data: dict, assessments: list, attendance: dict) -> str:
    """
    Generate a personalised performance report for a Karnataka school student.

    Args:
        student_data: Dict of student fields (name, class, school, etc.).
        assessments: List of assessment dicts with subject, marks, type.
        attendance: Dict with attendance counts and percentage.

    Returns:
        Formatted AI-generated report as a string (Markdown-compatible).
    """
    assessments_text = "\n".join(
        f"  - {a['subject']} | {a['assessment_type']} | "
        f"{a['marks_obtained']}/{a['max_marks']} ({a.get('percentage', 0):.1f}%) | "
        f"Chapter: {a.get('chapter', 'N/A')}"
        for a in assessments
    ) or "  No assessments recorded yet."

    prompt = f"""You are an expert educational analyst working with the Karnataka SATS 
(Student Achievement Tracking System) portal. Generate a comprehensive, empathetic 
student performance report for a teacher and parent review.

## Student Information
- Name: {student_data.get('name')}
- Class: {student_data.get('current_class')} | Section: {student_data.get('section', 'N/A')}
- School (DISE): {student_data.get('school_dise_code')}
- Gender: {student_data.get('gender')}
- Category: {student_data.get('caste_category')}

## Attendance Summary
- Total School Days: {attendance.get('total_days', 0)}
- Days Present: {attendance.get('present_days', 0)}
- Days Absent: {attendance.get('absent_days', 0)}
- Attendance Percentage: {attendance.get('attendance_percentage', 0):.1f}%

## Assessment Records
{assessments_text}

## Instructions
1. Summarise overall academic performance in 2-3 sentences.
2. Identify top 2 strong subjects and 2 areas needing improvement.
3. Comment on attendance and its possible impact on learning.
4. Give 3 actionable, Karnataka-curriculum-aligned (KSEEB/NEP 2020) recommendations 
   for the teacher to support this student.
5. Add a brief encouraging note for the student (suitable for Kannada-medium or 
   English-medium school context in Karnataka).
6. Format the output in clear sections with headings.
Keep the tone professional yet warm. The report should be readable by both 
the teacher and the student's parents."""

    return _generate(prompt)


def generate_class_summary(class_data: dict, students_assessment_summary: list) -> str:
    """
    Generate a class-level performance summary for the teacher.

    Args:
        class_data: Dict with class, section, school, teacher info.
        students_assessment_summary: List of per-student aggregate results.

    Returns:
        AI-generated class performance narrative.
    """
    top_students = sorted(
        students_assessment_summary, key=lambda s: s.get("average_percentage", 0), reverse=True
    )[:5]
    weak_students = sorted(
        students_assessment_summary, key=lambda s: s.get("average_percentage", 0)
    )[:5]

    top_text = "\n".join(
        f"  - {s['name']}: {s.get('average_percentage', 0):.1f}%"
        for s in top_students
    )
    weak_text = "\n".join(
        f"  - {s['name']}: {s.get('average_percentage', 0):.1f}%"
        for s in weak_students
    )

    prompt = f"""You are a senior educational analyst for Karnataka's SATS system. 
Generate a detailed class-level performance summary report for a teacher in Karnataka.

## Class Information
- Class: {class_data.get('current_class')} | Section: {class_data.get('section', 'N/A')}
- School DISE Code: {class_data.get('school_dise_code')}
- Total Students Assessed: {len(students_assessment_summary)}
- Class Average Performance: {
    sum(s.get('average_percentage', 0) for s in students_assessment_summary) / 
    max(len(students_assessment_summary), 1):.1f}%

## Top Performing Students
{top_text or "  No data available."}

## Students Needing Attention
{weak_text or "  No data available."}

## Instructions
1. Provide a concise overall class health assessment (2-3 sentences).
2. Highlight subjects where the class performs well collectively.
3. Identify subjects / chapters with the most widespread struggles.
4. Recommend 3 classroom strategies aligned with Karnataka state curriculum 
   (KSEEB, NEP 2020) to lift class performance.
5. Suggest how to structure remedial classes if needed.
6. Note any diversity considerations (gender, SC/ST/OBC representation) 
   if the data implies patterns.
Format with clear headings. Keep it practical and actionable for a Karnataka government school teacher."""

    return _generate(prompt)


def generate_attendance_alert(at_risk_students: list, school_info: dict) -> str:
    """
    Identify and explain attendance risks, suggest interventions.

    Args:
        at_risk_students: List of student dicts with attendance stats.
        school_info: Dict with school name, district, type.

    Returns:
        AI-generated attendance risk analysis.
    """
    student_lines = "\n".join(
        f"  - {s['name']} (SATS: {s['sats_id']}): "
        f"{s.get('attendance_percentage', 0):.1f}% | "
        f"Absent: {s.get('absent_days', 0)} days | "
        f"Class: {s.get('current_class', 'N/A')} | "
        f"Gender: {s.get('gender', 'N/A')} | "
        f"Category: {s.get('caste_category', 'N/A')}"
        for s in at_risk_students
    ) or "  No at-risk students identified."

    prompt = f"""You are a welfare and student support analyst for the Karnataka SATS portal.
Analyse the following attendance data for students at risk and provide actionable 
guidance for a Karnataka school teacher.

## School Context
- School: {school_info.get('name', 'Unknown')}
- District: {school_info.get('district', 'Karnataka')}
- School Type: {school_info.get('school_type', 'Government')}

## Students with Low Attendance (below 75%)
{student_lines}

## Instructions
1. Categorise risks: critical (<60%), serious (60-75%), at-risk (75-80%).
2. For each category, explain likely root causes in the Karnataka government 
   school context (agricultural seasons, festival seasons in Karnataka, 
   distance from school in rural taluk areas, economic factors).
3. Suggest specific, culturally appropriate interventions:
   - Home visit protocols
   - Engagement with local Panchayat / Ward members
   - Mid-day meal incentives
   - Engagement with parents / guardians
4. Recommend which students need immediate counsellor / Block Resource 
   Coordinator (BRC) escalation.
5. Suggest how to track improvement over the next 30 days.
Be sensitive to the socioeconomic context of Karnataka's rural and 
semi-urban government schools."""

    return _generate(prompt)


def generate_lesson_plan(
    subject: str,
    current_class: str,
    weak_chapters: list,
    teacher_name: str,
    academic_year: str,
) -> str:
    """
    Generate a tailored lesson plan based on student weak areas.

    Args:
        subject: Subject name.
        current_class: Class grade.
        weak_chapters: Chapters/topics where students performed poorly.
        teacher_name: Name of the requesting teacher.
        academic_year: Academic year string.

    Returns:
        AI-generated lesson plan as Markdown.
    """
    chapters_text = "\n".join(f"  - {ch}" for ch in weak_chapters) or "  (General weak performance)"

    prompt = f"""You are a master teacher trainer for Karnataka's Samagra Shiksha Abhiyana programme.
Create a detailed, practical lesson plan for a Karnataka government school teacher.

## Context
- Teacher: {teacher_name}
- Subject: {subject}
- Class: {current_class}
- Academic Year: {academic_year}
- Karnataka Curriculum: KSEEB / NEP 2020 aligned

## Chapters / Topics Where Students Are Struggling
{chapters_text}

## Instructions
Generate a structured 2-week lesson plan that includes:
1. **Learning Objectives** — SMART goals aligned to KSEEB outcomes for Class {current_class}.
2. **Daily Session Breakdown** (10 sessions × 45 minutes each):
   - Session title and topic
   - Teaching methodology (activity-based, group discussion, TLM use)
   - Assessment mini-activity for that session
3. **Teaching-Learning Materials (TLM)** to use — suggest low-cost, 
   locally available materials appropriate for Karnataka government schools.
4. **Differentiated Learning Strategies** — for students at different levels 
   (advanced, average, struggling).
5. **Formative Assessment checkpoints** — quick checks aligned with KSEEB FA norms.
6. **Home assignments** — simple, parent-friendly tasks (for both Kannada-medium 
   and English-medium contexts).
7. **Expected outcomes** — what students should demonstrate after 2 weeks.

Format as a clean, teacher-friendly plan. Use simple language. 
Include both Kannada-medium and English-medium teaching tips where applicable."""

    return _generate(prompt)
