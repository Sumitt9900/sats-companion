"""
core/models.py — SQLAlchemy ORM models for SATS Companion.

Entities:
  - School      : Karnataka government/aided/unaided schools
  - Teacher     : School teachers identified by KGID
  - Student     : Students identified by SATS ID
  - Attendance  : Daily attendance records
  - Assessment  : FA/SA and other assessment records
  - TransferCertificate : TC request lifecycle
"""
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, Float,
    ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
import enum

from core.databsae import Base


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class SchoolType(str, enum.Enum):
    GOVERNMENT = "government"
    AIDED = "aided"
    UNAIDED = "unaided"


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class CasteCategory(str, enum.Enum):
    GENERAL = "general"
    OBC = "obc"
    SC = "sc"
    ST = "st"


class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    HOLIDAY = "holiday"
    HALF_DAY = "half_day"


class AssessmentType(str, enum.Enum):
    FA1 = "FA1"
    FA2 = "FA2"
    FA3 = "FA3"
    FA4 = "FA4"
    SA1 = "SA1"
    SA2 = "SA2"
    UNIT_TEST = "unit_test"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    ANNUAL = "annual"


class TCStatus(str, enum.Enum):
    REQUESTED = "requested"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ISSUED = "issued"


class Designation(str, enum.Enum):
    HM = "headmaster"
    ASST_TEACHER = "assistant_teacher"
    GRAD_TEACHER = "graduate_teacher"
    PGT = "post_graduate_teacher"
    CRC = "cluster_resource_coordinator"
    BRC = "block_resource_coordinator"
    OTHER = "other"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    HEADMASTER = "headmaster"
    TEACHER = "teacher"
    DATA_ENTRY = "data_entry"


class SyncOperation(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class SyncStatus(str, enum.Enum):
    PENDING = "pending"
    SYNCED = "synced"
    CONFLICT = "conflict"
    ERROR = "error"
    SKIPPED = "skipped"


class SubmissionStatus(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# School
# ---------------------------------------------------------------------------
class School(Base):
    """
    Represents a Karnataka school registered in SATS/DISE.

    Primary key is the DISE (District Information System for Education) code,
    a unique 11-digit identifier assigned by MoE.
    """
    __tablename__ = "schools"

    dise_code = Column(String(20), primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    district = Column(String(100), nullable=False, index=True)
    taluk = Column(String(100), nullable=False)
    block = Column(String(100), nullable=True)
    village = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    pincode = Column(String(10), nullable=True)
    school_type = Column(Enum(SchoolType), nullable=False, default=SchoolType.GOVERNMENT)
    medium = Column(String(50), nullable=True)          # Kannada / English / Urdu etc.
    category = Column(String(50), nullable=True)        # Primary / High / PU etc.
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    teachers = relationship("Teacher", back_populates="school", lazy="select")
    students = relationship("Student", back_populates="school", lazy="select")


# ---------------------------------------------------------------------------
# Teacher
# ---------------------------------------------------------------------------
class Teacher(Base):
    """
    Represents a Karnataka government school teacher.

    KGID (Karnataka Government ID) is the unique employee identifier assigned
    by the state government. Teachers log in using their KGID.
    """
    __tablename__ = "teachers"

    id = Column(String(36), primary_key=True, default=_uuid)
    kgid = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)
    designation = Column(Enum(Designation), nullable=False, default=Designation.ASST_TEACHER)
    subject = Column(String(100), nullable=True)
    school_dise_code = Column(String(20), ForeignKey("schools.dise_code"), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    hashed_password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.TEACHER)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    school = relationship("School", back_populates="teachers")
    attendances_marked = relationship("Attendance", back_populates="marked_by_teacher", lazy="select")


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------
class Student(Base):
    """
    Represents a student enrolled in a Karnataka SATS-registered school.

    SATS ID is the unique identifier assigned by the Karnataka Student
    Achievement Tracking System portal.
    """
    __tablename__ = "students"

    sats_id = Column(String(30), primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    dob = Column(Date, nullable=True)
    gender = Column(Enum(Gender), nullable=False)
    current_class = Column(String(10), nullable=False)   # e.g. "8", "9A", "10"
    section = Column(String(5), nullable=True)
    school_dise_code = Column(String(20), ForeignKey("schools.dise_code"), nullable=False)
    aadhaar = Column(String(12), nullable=True)          # Optional, stored masked
    caste_category = Column(Enum(CasteCategory), nullable=False, default=CasteCategory.GENERAL)
    religion = Column(String(50), nullable=True)
    # Parent / Guardian info
    father_name = Column(String(150), nullable=True)
    mother_name = Column(String(150), nullable=True)
    guardian_name = Column(String(150), nullable=True)
    guardian_phone = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    # Flags
    is_active = Column(Boolean, default=True, nullable=False)   # False = withdrawn
    is_transferred = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    school = relationship("School", back_populates="students")
    attendances = relationship("Attendance", back_populates="student", lazy="select")
    assessments = relationship("Assessment", back_populates="student", lazy="select")
    transfer_certificates = relationship("TransferCertificate", back_populates="student", lazy="select")


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------
class Attendance(Base):
    """
    Daily attendance record for a student.

    One record per student per date. Duplicate inserts on same
    (student, date) are blocked by a unique constraint.
    """
    __tablename__ = "attendances"
    __table_args__ = (
        UniqueConstraint("student_sats_id", "attendance_date", name="uq_student_date"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    student_sats_id = Column(String(30), ForeignKey("students.sats_id"), nullable=False, index=True)
    attendance_date = Column(Date, nullable=False, index=True)
    status = Column(Enum(AttendanceStatus), nullable=False, default=AttendanceStatus.PRESENT)
    marked_by_teacher_id = Column(String(36), ForeignKey("teachers.id"), nullable=True)
    remarks = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    student = relationship("Student", back_populates="attendances")
    marked_by_teacher = relationship("Teacher", back_populates="attendances_marked")


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------
class Assessment(Base):
    """
    Assessment / exam result for a student in a specific subject.

    Supports both formative (FA) and summative (SA) assessments along with
    chapter/lesson-level granularity.
    """
    __tablename__ = "assessments"

    id = Column(String(36), primary_key=True, default=_uuid)
    student_sats_id = Column(String(30), ForeignKey("students.sats_id"), nullable=False, index=True)
    subject = Column(String(100), nullable=False, index=True)
    chapter = Column(String(200), nullable=True)         # Chapter or lesson name
    assessment_type = Column(Enum(AssessmentType), nullable=False)
    marks_obtained = Column(Float, nullable=False)
    max_marks = Column(Float, nullable=False)
    assessment_date = Column(Date, nullable=False, index=True)
    academic_year = Column(String(10), nullable=False)   # e.g. "2024-25"
    recorded_by_teacher_id = Column(String(36), ForeignKey("teachers.id"), nullable=True)
    remarks = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    student = relationship("Student", back_populates="assessments")
    recorded_by_teacher = relationship("Teacher")

    @property
    def percentage(self) -> float:
        """Return marks as percentage, rounded to 2 decimal places."""
        if self.max_marks == 0:
            return 0.0
        return round((self.marks_obtained / self.max_marks) * 100, 2)


# ---------------------------------------------------------------------------
# Transfer Certificate
# ---------------------------------------------------------------------------
class TransferCertificate(Base):
    """
    Transfer Certificate (TC) request and lifecycle tracking.

    A TC is raised when a student moves from one Karnataka school to another.
    Approval is done by the Headmaster (HM) or an admin.
    """
    __tablename__ = "transfer_certificates"

    id = Column(String(36), primary_key=True, default=_uuid)
    student_sats_id = Column(String(30), ForeignKey("students.sats_id"), nullable=False, index=True)
    issuing_school_dise = Column(String(20), ForeignKey("schools.dise_code"), nullable=False)
    receiving_school_dise = Column(String(20), nullable=True)  # May not be known at request time
    reason = Column(Text, nullable=True)
    status = Column(Enum(TCStatus), nullable=False, default=TCStatus.REQUESTED)
    requested_by_teacher_id = Column(String(36), ForeignKey("teachers.id"), nullable=True)
    approved_by_teacher_id = Column(String(36), ForeignKey("teachers.id"), nullable=True)
    request_date = Column(Date, nullable=False, default=date.today)
    approval_date = Column(Date, nullable=True)
    issue_date = Column(Date, nullable=True)
    tc_number = Column(String(50), nullable=True, unique=True)  # Official TC serial number
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    student = relationship("Student", back_populates="transfer_certificates")
    issuing_school = relationship("School", foreign_keys=[issuing_school_dise])
    requested_by = relationship("Teacher", foreign_keys=[requested_by_teacher_id])
    approved_by = relationship("Teacher", foreign_keys=[approved_by_teacher_id])


# ---------------------------------------------------------------------------
# SyncQueue — persists every local mutation for offline-first sync
# ---------------------------------------------------------------------------
class SyncQueue(Base):
    """
    Offline-first sync queue. Every mutation to any entity is recorded here
    before (or instead of) being applied to the central database.

    When connectivity is restored, the sync engine flushes this queue to the
    central SATS gateway, using cryptographic checksums to verify integrity.
    """
    __tablename__ = "sync_queue"

    id = Column(String(36), primary_key=True, default=_uuid)
    operation = Column(Enum(SyncOperation), nullable=False)
    entity_type = Column(String(50), nullable=False, index=True)  # e.g. "student", "attendance"
    entity_id = Column(String(50), nullable=False, index=True)
    payload_json = Column(Text, nullable=False)                    # JSON-serialised entity data
    checksum_sha256 = Column(String(64), nullable=False)           # SHA-256 of payload_json
    sync_status = Column(Enum(SyncStatus), nullable=False, default=SyncStatus.PENDING, index=True)
    conflict_data = Column(Text, nullable=True)                    # Server version on conflict
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    local_device_id = Column(String(100), nullable=True)           # Which device created this
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    synced_at = Column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# SyncLog — audit trail of synchronisation events
# ---------------------------------------------------------------------------
class SyncLog(Base):
    """
    Audit log for each sync session. Tracks how many records were pushed,
    pulled, conflicted, and any error messages.
    """
    __tablename__ = "sync_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), nullable=False, unique=True)   # UUID per sync session
    triggered_by_teacher_id = Column(String(36), ForeignKey("teachers.id"), nullable=True)
    pushed_count = Column(Integer, default=0, nullable=False)
    pulled_count = Column(Integer, default=0, nullable=False)
    conflict_count = Column(Integer, default=0, nullable=False)
    error_count = Column(Integer, default=0, nullable=False)
    sync_mode = Column(String(20), nullable=False, default="manual")  # "manual" | "auto"
    duration_seconds = Column(Float, nullable=True)
    error_details = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    success = Column(Boolean, default=False, nullable=False)


# ---------------------------------------------------------------------------
# MarksBatchSubmission — Teacher ingested marks awaiting HM approval & SATS sync
# ---------------------------------------------------------------------------
class MarksBatchSubmission(Base):
    """
    Submissions of marks ingested by teachers (via Excel, CSV, PDF, or Photo OCR)
    awaiting review, verification, and SATS upload by the Headmaster.
    """
    __tablename__ = "marks_batch_submissions"

    id = Column(String(36), primary_key=True, default=_uuid)
    school_dise_code = Column(String(20), ForeignKey("schools.dise_code"), nullable=False, index=True)
    submitted_by_teacher_id = Column(String(36), ForeignKey("teachers.id"), nullable=False, index=True)
    reviewed_by_teacher_id = Column(String(36), ForeignKey("teachers.id"), nullable=True)

    academic_year = Column(String(10), nullable=False, default="2026-27")
    target_class = Column(String(10), nullable=True)
    section = Column(String(5), nullable=True)
    subject = Column(String(100), nullable=False)
    assessment_type = Column(String(50), nullable=False)
    max_marks = Column(Float, nullable=False, default=20.0)
    total_records = Column(Integer, nullable=False, default=0)
    source_filename = Column(String(255), nullable=True)
    records_json = Column(Text, nullable=False)  # JSON-encoded array of candidate mark records
    status = Column(Enum(SubmissionStatus), nullable=False, default=SubmissionStatus.PENDING_APPROVAL, index=True)
    submission_notes = Column(Text, nullable=True)
    hm_review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    school = relationship("School")
    submitted_by = relationship("Teacher", foreign_keys=[submitted_by_teacher_id])
    reviewed_by = relationship("Teacher", foreign_keys=[reviewed_by_teacher_id])

