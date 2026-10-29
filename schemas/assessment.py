"""
schemas/assessment.py — Pydantic schemas for Assessment entity.
"""
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from core.models import AssessmentType


class AssessmentCreate(BaseModel):
    """Request body for recording an assessment result."""

    student_sats_id: str = Field(..., max_length=30)
    subject: str = Field(..., max_length=100)
    chapter: Optional[str] = Field(None, max_length=200)
    assessment_type: AssessmentType
    marks_obtained: float = Field(..., ge=0)
    max_marks: float = Field(..., gt=0)
    assessment_date: date
    academic_year: str = Field(..., max_length=10, description='e.g. "2024-25"')
    remarks: Optional[str] = Field(None, max_length=300)

    @model_validator(mode="after")
    def check_marks(self):
        if self.marks_obtained > self.max_marks:
            raise ValueError("marks_obtained cannot exceed max_marks")
        return self


class AssessmentResponse(BaseModel):
    """Response schema for an assessment record."""

    id: str
    student_sats_id: str
    subject: str
    chapter: Optional[str] = None
    assessment_type: AssessmentType
    marks_obtained: float
    max_marks: float
    percentage: float
    assessment_date: date
    academic_year: str
    recorded_by_teacher_id: Optional[str] = None
    remarks: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SubjectSummary(BaseModel):
    """Aggregated subject performance for a student or class."""

    subject: str
    assessment_count: int
    average_percentage: float
    highest_percentage: float
    lowest_percentage: float
    weak_chapters: List[str] = []
