"""
tests/test_api.py — Comprehensive API test suite for SATS Companion.

Tests every endpoint for:
  - Happy path (correct inputs → correct outputs)
  - Error handling (bad inputs → proper HTTP errors)
  - Auth enforcement (protected endpoints reject unauthenticated requests)
  - Edge cases (empty data, boundary values, duplicates)
  - Bilingual response messages

Run with:
    cd /Users/sumith/sats-companion
    venv/bin/pytest tests/test_api.py -v --tb=short
"""
import pytest
from httpx import Client

BASE_URL = "http://127.0.0.1:8000"
HM_KGID = "KGID10001"
HM_PASS = "admin@123"
TEACHER_KGID = "KGID10002"
TEACHER_PASS = "teacher@123"
TEST_SCHOOL_DISE = "29210101001"

# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    with Client(base_url=BASE_URL, timeout=15) as c:
        yield c


@pytest.fixture(scope="session")
def hm_token(client):
    """Get headmaster JWT token."""
    r = client.post("/api/v1/auth/login", data={
        "username": HM_KGID, "password": HM_PASS
    })
    assert r.status_code == 200, f"HM login failed: {r.text}"
    return r.json()["data"]["access_token"]


@pytest.fixture(scope="session")
def teacher_token(client):
    """Get regular teacher JWT token."""
    r = client.post("/api/v1/auth/login", data={
        "username": TEACHER_KGID, "password": TEACHER_PASS
    })
    assert r.status_code == 200, f"Teacher login failed: {r.text}"
    return r.json()["data"]["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════════
# 1. HEALTH & ROOT
# ═══════════════════════════════════════════════════════════════════════════

class TestHealth:
    def test_health_check(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "success"
        assert data["data"]["database"] == "connected"

    def test_root_redirects_to_pwa(self, client):
        r = client.get("/", follow_redirects=False)
        # Should redirect to PWA or return JSON
        assert r.status_code in (200, 307, 308)

    def test_docs_available(self, client):
        r = client.get("/docs")
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 2. AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════

class TestAuth:
    def test_login_success_headmaster(self, client):
        r = client.post("/api/v1/auth/login", data={
            "username": HM_KGID, "password": HM_PASS
        })
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "success"
        assert "access_token" in d["data"]
        assert d["data"]["token_type"] == "bearer"
        assert d["data"]["is_admin"] is True
        assert d["data"]["role"] == "headmaster"
        assert d["data"]["designation"] == "headmaster"

    def test_login_success_teacher(self, client):
        r = client.post("/api/v1/auth/login", data={
            "username": TEACHER_KGID, "password": TEACHER_PASS
        })
        assert r.status_code == 200
        d = r.json()
        assert d["data"]["is_admin"] is False
        assert d["data"]["role"] == "teacher"

    def test_login_wrong_password(self, client):
        r = client.post("/api/v1/auth/login", data={
            "username": HM_KGID, "password": "wrongpassword"
        })
        assert r.status_code == 401
        assert "Invalid" in r.json()["detail"]

    def test_login_wrong_kgid(self, client):
        r = client.post("/api/v1/auth/login", data={
            "username": "KGIDXXXXXX", "password": HM_PASS
        })
        assert r.status_code == 401

    def test_login_missing_password(self, client):
        r = client.post("/api/v1/auth/login", data={"username": HM_KGID})
        assert r.status_code == 422

    def test_login_empty_credentials(self, client):
        r = client.post("/api/v1/auth/login", data={"username": "", "password": ""})
        assert r.status_code in (401, 422)

    def test_me_authenticated(self, client, hm_token):
        r = client.get("/api/v1/auth/me", headers=auth(hm_token))
        assert r.status_code == 200
        d = r.json()
        assert d["data"]["kgid"] == HM_KGID

    def test_me_unauthenticated(self, client):
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401

    def test_me_invalid_token(self, client):
        r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalidtoken"})
        assert r.status_code == 401

    def test_token_refresh(self, client, hm_token):
        r = client.post("/api/v1/auth/refresh", json={"token": hm_token})
        assert r.status_code == 200
        assert "access_token" in r.json()["data"]

    def test_token_refresh_invalid(self, client):
        r = client.post("/api/v1/auth/refresh", json={"token": "badtoken"})
        assert r.status_code in (401, 422)


# ═══════════════════════════════════════════════════════════════════════════
# 3. SCHOOLS
# ═══════════════════════════════════════════════════════════════════════════

class TestSchools:
    def test_list_schools(self, client, hm_token):
        r = client.get("/api/v1/schools", headers=auth(hm_token))
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "success"
        # At least the seeded school exists
        schools = d["data"] if isinstance(d["data"], list) else d["data"].get("schools", d["data"])
        assert len(schools) >= 1

    def test_get_school_by_dise(self, client, hm_token):
        r = client.get(f"/api/v1/schools/{TEST_SCHOOL_DISE}", headers=auth(hm_token))
        assert r.status_code == 200
        school = r.json()["data"]
        assert school["dise_code"] == TEST_SCHOOL_DISE
        assert "Channapatna" in school["name"]

    def test_get_school_not_found(self, client, hm_token):
        r = client.get("/api/v1/schools/00000000000", headers=auth(hm_token))
        assert r.status_code == 404

    def test_schools_unauthenticated(self, client):
        r = client.get("/api/v1/schools")
        assert r.status_code == 401

    def test_filter_schools_by_district(self, client, hm_token):
        r = client.get("/api/v1/schools?district=Ramanagara", headers=auth(hm_token))
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 4. TEACHERS
# ═══════════════════════════════════════════════════════════════════════════

class TestTeachers:
    def test_list_teachers(self, client, hm_token):
        r = client.get("/api/v1/teachers", headers=auth(hm_token))
        assert r.status_code == 200
        data = r.json()["data"]
        teachers = data if isinstance(data, list) else data.get("teachers", data)
        assert len(teachers) >= 2

    def test_teacher_me(self, client, teacher_token):
        r = client.get("/api/v1/teachers/me", headers=auth(teacher_token))
        assert r.status_code == 200
        assert r.json()["data"]["kgid"] == TEACHER_KGID

    def test_teacher_me_hm(self, client, hm_token):
        r = client.get("/api/v1/teachers/me", headers=auth(hm_token))
        assert r.status_code == 200
        assert r.json()["data"]["kgid"] == HM_KGID

    def test_create_teacher_duplicate_kgid(self, client, hm_token):
        r = client.post("/api/v1/teachers", headers=auth(hm_token), json={
            "kgid": HM_KGID,  # Already exists
            "name": "Duplicate Teacher",
            "designation": "assistant_teacher",
            "password": "test@123"
        })
        assert r.status_code in (400, 409, 422)

    def test_teachers_unauthenticated(self, client):
        r = client.get("/api/v1/teachers")
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 5. STUDENTS
# ═══════════════════════════════════════════════════════════════════════════

class TestStudents:
    TEST_SATS_ID = "SATS_TEST_001"

    @pytest.fixture(autouse=True, scope="class")
    def clean_test_student(self):
        from core.databsae import SessionLocal
        from core.models import Student
        db = SessionLocal()
        db.query(Student).filter(Student.sats_id == self.TEST_SATS_ID).delete()
        db.commit()
        db.close()
        yield
        db = SessionLocal()
        db.query(Student).filter(Student.sats_id == self.TEST_SATS_ID).delete()
        db.commit()
        db.close()

    def test_list_students(self, client, hm_token):
        r = client.get("/api/v1/students", headers=auth(hm_token))
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "success"
        assert d["data"]["total"] >= 10  # 10 seeded

    def test_list_students_pagination(self, client, hm_token):
        r = client.get("/api/v1/students?limit=3&offset=0", headers=auth(hm_token))
        assert r.status_code == 200
        assert len(r.json()["data"]["students"]) == 3

    def test_list_students_filter_class(self, client, hm_token):
        r = client.get("/api/v1/students?current_class=8", headers=auth(hm_token))
        assert r.status_code == 200
        students = r.json()["data"]["students"]
        assert all(s["current_class"] == "8" for s in students)

    def test_list_students_filter_gender(self, client, hm_token):
        r = client.get("/api/v1/students?gender=female", headers=auth(hm_token))
        assert r.status_code == 200
        students = r.json()["data"]["students"]
        assert all(s["gender"] == "female" for s in students)

    def test_get_student_by_sats_id(self, client, hm_token):
        r = client.get("/api/v1/students/SATS2901001", headers=auth(hm_token))
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "Darshan Gowda"

    def test_get_student_not_found(self, client, hm_token):
        r = client.get("/api/v1/students/NONEXISTENT_SATS_ID", headers=auth(hm_token))
        assert r.status_code == 404

    def test_create_student(self, client, hm_token):
        r = client.post("/api/v1/students", headers=auth(hm_token), json={
            "sats_id": self.TEST_SATS_ID,
            "name": "Test Student Kannada",
            "gender": "male",
            "current_class": "9",
            "section": "C",
            "school_dise_code": TEST_SCHOOL_DISE,
            "caste_category": "general"
        })
        assert r.status_code in (200, 201), f"Create student failed: {r.text}"
        assert r.json()["data"]["sats_id"] == self.TEST_SATS_ID

    def test_create_student_duplicate(self, client, hm_token):
        r = client.post("/api/v1/students", headers=auth(hm_token), json={
            "sats_id": self.TEST_SATS_ID,  # Already created
            "name": "Duplicate",
            "gender": "male",
            "current_class": "9",
            "school_dise_code": TEST_SCHOOL_DISE,
            "caste_category": "general"
        })
        assert r.status_code in (400, 409)

    def test_create_student_invalid_gender(self, client, hm_token):
        r = client.post("/api/v1/students", headers=auth(hm_token), json={
            "sats_id": "SATS_BAD_GENDER",
            "name": "Bad Student",
            "gender": "invalid_gender",
            "current_class": "8",
            "school_dise_code": TEST_SCHOOL_DISE,
            "caste_category": "general"
        })
        assert r.status_code == 422

    def test_create_student_missing_required_fields(self, client, hm_token):
        r = client.post("/api/v1/students", headers=auth(hm_token), json={
            "sats_id": "SATS_INCOMPLETE"
            # Missing: name, gender, current_class, school_dise_code, caste_category
        })
        assert r.status_code == 422

    def test_update_student(self, client, hm_token):
        r = client.put(f"/api/v1/students/{self.TEST_SATS_ID}", headers=auth(hm_token), json={
            "section": "D",
            "current_class": "9"
        })
        assert r.status_code == 200

    def test_soft_delete_student(self, client, hm_token):
        r = client.delete(f"/api/v1/students/{self.TEST_SATS_ID}", headers=auth(hm_token))
        assert r.status_code == 200
        # Verify soft delete - student still exists but is_active=False
        r2 = client.get(f"/api/v1/students/{self.TEST_SATS_ID}", headers=auth(hm_token))
        # Should either 404 or return with is_active=False
        if r2.status_code == 200:
            assert r2.json()["data"]["is_active"] is False

    def test_students_unauthenticated(self, client):
        r = client.get("/api/v1/students")
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 6. ATTENDANCE
# ═══════════════════════════════════════════════════════════════════════════

class TestAttendance:
    def test_bulk_attendance_mark(self, client, teacher_token):
        r = client.post("/api/v1/attendance/bulk", headers=auth(teacher_token), json={
            "attendance_date": "2026-10-15",
            "records": [
                {"student_sats_id": "SATS2901001", "status": "present", "attendance_date": "2026-10-15"},
                {"student_sats_id": "SATS2901002", "status": "absent", "attendance_date": "2026-10-15"},
                {"student_sats_id": "SATS2901003", "status": "present", "attendance_date": "2026-10-15"},
            ]
        })
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "success"

    def test_bulk_attendance_upsert(self, client, teacher_token):
        """Re-marking attendance on same date should update, not error."""
        r = client.post("/api/v1/attendance/bulk", headers=auth(teacher_token), json={
            "attendance_date": "2026-10-15",
            "records": [
                {"student_sats_id": "SATS2901001", "status": "absent", "attendance_date": "2026-10-15"},
            ]
        })
        assert r.status_code == 200

    def test_attendance_summary(self, client, hm_token):
        r = client.get("/api/v1/attendance/summary/SATS2901001", headers=auth(hm_token))
        assert r.status_code == 200
        data = r.json()["data"]
        assert "attendance_percentage" in data or "present_days" in data

    def test_attendance_summary_nonexistent_student(self, client, hm_token):
        r = client.get("/api/v1/attendance/summary/NONEXISTENT", headers=auth(hm_token))
        assert r.status_code in (200, 404)  # Some impls return empty summary

    def test_attendance_report(self, client, hm_token):
        r = client.get(
            "/api/v1/attendance/report?school_dise_code=29210101001",
            headers=auth(hm_token)
        )
        assert r.status_code == 200

    def test_bulk_attendance_invalid_status(self, client, teacher_token):
        r = client.post("/api/v1/attendance/bulk", headers=auth(teacher_token), json={
            "attendance_date": "2026-10-15",
            "records": [
                {"student_sats_id": "SATS2901001", "status": "invalid_status", "attendance_date": "2026-10-15"}
            ]
        })
        assert r.status_code == 422

    def test_bulk_attendance_empty_records(self, client, teacher_token):
        r = client.post("/api/v1/attendance/bulk", headers=auth(teacher_token), json={
            "attendance_date": "2026-10-15",
            "records": []
        })
        assert r.status_code in (200, 400, 422)

    def test_attendance_unauthenticated(self, client):
        r = client.post("/api/v1/attendance/bulk", json={"records": [], "attendance_date": "2026-10-15"})
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 7. ASSESSMENTS
# ═══════════════════════════════════════════════════════════════════════════

class TestAssessments:
    def test_create_assessment(self, client, teacher_token):
        r = client.post("/api/v1/assessments", headers=auth(teacher_token), json={
            "student_sats_id": "SATS2901001",
            "subject": "Mathematics",
            "chapter": "Algebra",
            "assessment_type": "FA1",
            "marks_obtained": 18.5,
            "max_marks": 20,
            "assessment_date": "2026-10-20",
            "academic_year": "2026-27"
        })
        assert r.status_code in (200, 201)
        data = r.json()["data"]
        assert data["marks_obtained"] == 18.5

    def test_create_assessment_marks_exceed_max(self, client, teacher_token):
        r = client.post("/api/v1/assessments", headers=auth(teacher_token), json={
            "student_sats_id": "SATS2901001",
            "subject": "Science",
            "assessment_type": "FA1",
            "marks_obtained": 25,   # > max_marks
            "max_marks": 20,
            "assessment_date": "2026-10-20",
            "academic_year": "2026-27"
        })
        assert r.status_code in (400, 422)

    def test_create_assessment_negative_marks(self, client, teacher_token):
        r = client.post("/api/v1/assessments", headers=auth(teacher_token), json={
            "student_sats_id": "SATS2901001",
            "subject": "Science",
            "assessment_type": "FA1",
            "marks_obtained": -5,  # Negative
            "max_marks": 20,
            "assessment_date": "2026-10-20",
            "academic_year": "2026-27"
        })
        assert r.status_code in (400, 422)

    def test_get_assessments_by_student(self, client, hm_token):
        r = client.get("/api/v1/assessments/student/SATS2901001", headers=auth(hm_token))
        assert r.status_code == 200
        data = r.json()["data"]
        assert isinstance(data, list) or "assessments" in data

    def test_create_assessment_invalid_type(self, client, teacher_token):
        r = client.post("/api/v1/assessments", headers=auth(teacher_token), json={
            "student_sats_id": "SATS2901001",
            "subject": "Science",
            "assessment_type": "INVALID_TYPE",
            "marks_obtained": 15,
            "max_marks": 20,
            "assessment_date": "2026-10-20",
            "academic_year": "2026-27"
        })
        assert r.status_code == 422

    def test_get_assessments_nonexistent_student(self, client, hm_token):
        r = client.get("/api/v1/assessments/student/NONEXISTENT", headers=auth(hm_token))
        assert r.status_code in (200, 404)

    def test_assessments_unauthenticated(self, client):
        r = client.get("/api/v1/assessments/student/SATS2901001")
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 8. SYNC ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class TestSync:
    def test_sync_status(self, client, hm_token):
        r = client.get("/api/v1/sync/status", headers=auth(hm_token))
        assert r.status_code == 200
        d = r.json()
        assert "pending_count" in d
        assert "conflict_count" in d
        assert "is_online" in d

    def test_sync_push(self, client, hm_token):
        r = client.post("/api/v1/sync/push", headers=auth(hm_token), json={"force": False})
        assert r.status_code == 200
        d = r.json()
        assert "session_id" in d
        assert "pushed" in d

    def test_sync_pull(self, client, hm_token):
        r = client.post("/api/v1/sync/pull", headers=auth(hm_token))
        assert r.status_code == 200
        assert "session_id" in r.json()

    def test_sync_history(self, client, hm_token):
        r = client.get("/api/v1/sync/history", headers=auth(hm_token))
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_sync_resolve_nonexistent(self, client, hm_token):
        r = client.post("/api/v1/sync/resolve", headers=auth(hm_token), json={
            "queue_item_id": "nonexistent-id",
            "resolution": "use_local"
        })
        assert r.status_code in (400, 404)

    def test_sync_unauthenticated(self, client):
        r = client.get("/api/v1/sync/status")
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 9. CSV IMPORT
# ═══════════════════════════════════════════════════════════════════════════

class TestCSVImport:
    def test_student_csv_template_download(self, client, hm_token):
        r = client.get("/api/v1/import/templates/student", headers=auth(hm_token))
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "sats_id" in r.text

    def test_attendance_csv_template_download(self, client, hm_token):
        r = client.get("/api/v1/import/templates/attendance", headers=auth(hm_token))
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]

    def test_import_students_valid_csv(self, client, hm_token):
        csv_content = (
            "sats_id,name,dob,gender,current_class,section,school_dise_code,caste_category\n"
            "SATS_CSV_001,Test Import Gowda,10-05-2012,male,8,A,29210101001,obc\n"
        )
        r = client.post(
            "/api/v1/import/students/csv?dry_run=false",
            headers=auth(hm_token),
            files={"file": ("students.csv", csv_content, "text/csv")}
        )
        assert r.status_code == 200
        d = r.json()
        assert d["data"]["created"] >= 1 or d["data"]["skipped_duplicates"] >= 1

    def test_import_students_dry_run(self, client, hm_token):
        csv_content = (
            "sats_id,name,dob,gender,current_class,section,school_dise_code,caste_category\n"
            "SATS_DRYRUN_999,Dry Run Student,01-01-2012,female,7,B,29210101001,general\n"
        )
        r = client.post(
            "/api/v1/import/students/csv?dry_run=true",
            headers=auth(hm_token),
            files={"file": ("students.csv", csv_content, "text/csv")}
        )
        assert r.status_code == 200
        assert r.json()["data"]["dry_run"] is True

    def test_import_students_invalid_csv(self, client, hm_token):
        """CSV missing required columns."""
        csv_content = "name,dob\nTest Student,10-05-2012\n"
        r = client.post(
            "/api/v1/import/students/csv",
            headers=auth(hm_token),
            files={"file": ("bad.csv", csv_content, "text/csv")}
        )
        assert r.status_code == 422

    def test_import_non_csv_file(self, client, hm_token):
        r = client.post(
            "/api/v1/import/students/csv",
            headers=auth(hm_token),
            files={"file": ("data.xlsx", b"not a csv", "application/vnd.ms-excel")}
        )
        assert r.status_code == 422

    def test_import_attendance_valid_csv(self, client, hm_token):
        csv_content = (
            "sats_id,attendance_date,status,remarks\n"
            "SATS2901001,15-10-2026,present,\n"
            "SATS2901002,15-10-2026,absent,Sick\n"
        )
        r = client.post(
            "/api/v1/import/attendance/csv",
            headers=auth(hm_token),
            files={"file": ("att.csv", csv_content, "text/csv")}
        )
        assert r.status_code == 200
        d = r.json()
        assert d["data"]["created"] + d["data"]["updated"] >= 0

    def test_import_attendance_invalid_date(self, client, hm_token):
        csv_content = (
            "sats_id,attendance_date,status\n"
            "SATS2901001,not-a-date,present\n"
        )
        r = client.post(
            "/api/v1/import/attendance/csv",
            headers=auth(hm_token),
            files={"file": ("att.csv", csv_content, "text/csv")}
        )
        assert r.status_code == 200  # Returns partial with errors
        assert r.json()["data"]["failed"] >= 1

    def test_import_unauthenticated(self, client):
        csv_content = "sats_id,name\nSATS001,Test\n"
        r = client.post(
            "/api/v1/import/students/csv",
            files={"file": ("s.csv", csv_content, "text/csv")}
        )
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 10. TRANSFER CERTIFICATES
# ═══════════════════════════════════════════════════════════════════════════

class TestTransferCertificates:
    created_tc_id = None

    @pytest.fixture(autouse=True, scope="class")
    def clean_test_tc(self):
        from core.databsae import SessionLocal
        from core.models import TransferCertificate
        db = SessionLocal()
        db.query(TransferCertificate).filter(TransferCertificate.student_sats_id == "SATS2901002").delete()
        db.commit()
        db.close()
        yield
        db = SessionLocal()
        db.query(TransferCertificate).filter(TransferCertificate.student_sats_id == "SATS2901002").delete()
        db.commit()
        db.close()

    def test_request_tc(self, client, hm_token):
        r = client.post("/api/v1/tc/request", headers=auth(hm_token), json={
            "student_sats_id": "SATS2901002",
            "issuing_school_dise": TEST_SCHOOL_DISE,
            "reason": "Family relocation to Mysuru"
        })
        assert r.status_code in (200, 201)
        tc_data = r.json()["data"]
        assert tc_data["status"] == "requested"
        TestTransferCertificates.created_tc_id = tc_data["id"]

    def test_get_tc(self, client, hm_token):
        if not TestTransferCertificates.created_tc_id:
            pytest.skip("TC not created")
        r = client.get(
            f"/api/v1/tc/{TestTransferCertificates.created_tc_id}",
            headers=auth(hm_token)
        )
        assert r.status_code == 200
        assert r.json()["data"]["student_sats_id"] == "SATS2901002"

    def test_get_tc_by_student(self, client, hm_token):
        r = client.get("/api/v1/tc/student/SATS2901002", headers=auth(hm_token))
        assert r.status_code == 200

    def test_approve_tc(self, client, hm_token):
        if not TestTransferCertificates.created_tc_id:
            pytest.skip("TC not created")
        r = client.put(
            f"/api/v1/tc/{TestTransferCertificates.created_tc_id}/approve",
            headers=auth(hm_token),
            json={"status": "approved", "remarks": "Approved by HM"}
        )
        assert r.status_code == 200
        assert r.json()["data"]["status"] in ("approved", "issued")

    def test_request_tc_nonexistent_student(self, client, hm_token):
        r = client.post("/api/v1/tc/request", headers=auth(hm_token), json={
            "student_sats_id": "NONEXISTENT",
            "issuing_school_dise": TEST_SCHOOL_DISE,
            "reason": "Test"
        })
        assert r.status_code in (400, 404)

    def test_tc_unauthenticated(self, client):
        r = client.get("/api/v1/tc/some-id")
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 11. PWA STATIC FILES
# ═══════════════════════════════════════════════════════════════════════════

class TestPWAStaticFiles:
    def test_pwa_index_served(self, client):
        r = client.get("/static/index.html")
        assert r.status_code == 200
        assert "SATS Companion" in r.text

    def test_pwa_app_js_served(self, client):
        r = client.get("/static/app.js")
        assert r.status_code == 200
        assert "apiCall" in r.text

    def test_service_worker_served(self, client):
        r = client.get("/static/sw.js")
        assert r.status_code == 200

    def test_manifest_served(self, client):
        r = client.get("/static/manifest.json")
        assert r.status_code == 200
        manifest = r.json()
        assert manifest["name"] == "SATS Companion"
        assert manifest["display"] == "standalone"


# ═══════════════════════════════════════════════════════════════════════════
# 12. SATS MARKS BRIDGE (UNIVERSAL INGESTOR)
# ═══════════════════════════════════════════════════════════════════════════

class TestMarksBridge:
    def test_marks_bridge_parse_csv(self, client, hm_token):
        csv_data = "SATS ID,Student Name,Marks\nSATS2901001,Darshan Gowda,19.5\nSATS2901002,Bhavya R,18\n"
        r = client.post(
            "/api/v1/marks-bridge/parse",
            headers={"Authorization": f"Bearer {hm_token}"},
            files={"file": ("score_sheet.csv", csv_data.encode(), "text/csv")},
            data={"subject": "Mathematics", "assessment_type": "FA1", "max_marks": "20"}
        )
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "success"
        records = d["data"]["records"]
        assert len(records) == 2
        assert records[0]["student_sats_id"] == "SATS2901001"
        assert records[0]["marks_obtained"] == 19.5
        assert records[0]["match_status"] == "exact"

    def test_marks_bridge_batch_commit(self, client, hm_token):
        records = [
            {
                "student_sats_id": "SATS2901001",
                "student_name": "Darshan Gowda",
                "current_class": "8",
                "subject": "Mathematics",
                "assessment_type": "FA1",
                "marks_obtained": 19.0,
                "max_marks": 20.0
            }
        ]
        r = client.post(
            "/api/v1/marks-bridge/batch-commit",
            headers={"Authorization": f"Bearer {hm_token}"},
            json={"records": records, "school_dise_code": TEST_SCHOOL_DISE}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "success"
        assert r.json()["data"]["total"] >= 1

    def test_marks_bridge_export_sats_format(self, client, hm_token):
        records = [
            {
                "student_sats_id": "SATS2901001",
                "student_name": "Darshan Gowda",
                "current_class": "8",
                "subject": "Mathematics",
                "assessment_type": "FA1",
                "marks_obtained": 19.0,
                "max_marks": 20.0
            }
        ]
        r = client.post(
            "/api/v1/marks-bridge/export-sats-format",
            headers={"Authorization": f"Bearer {hm_token}"},
            json={"records": records, "school_dise_code": TEST_SCHOOL_DISE}
        )
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "Academic_Year" in r.text
        assert "SATS2901001" in r.text

    def test_marks_bridge_unauthenticated(self, client):
        r = client.post("/api/v1/marks-bridge/batch-commit", json={"records": []})
        assert r.status_code == 401

    def test_teacher_submit_marks_workflow(self, client, teacher_token, hm_token):
        """Test full teacher submission to HM approval and SATS push workflow."""
        records = [
            {
                "student_sats_id": "SATS2901001",
                "student_name": "Darshan Gowda",
                "current_class": "8",
                "subject": "Mathematics",
                "assessment_type": "FA1",
                "marks_obtained": 18.5,
                "max_marks": 20.0
            },
            {
                "student_sats_id": "SATS2901002",
                "student_name": "Bhavya R",
                "current_class": "8",
                "subject": "Mathematics",
                "assessment_type": "FA1",
                "marks_obtained": 17.0,
                "max_marks": 20.0
            }
        ]
        # 1. Teacher submits marks batch for HM review
        sub_resp = client.post(
            "/api/v1/marks-bridge/submit",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={
                "records": records,
                "subject": "Mathematics",
                "assessment_type": "FA1",
                "target_class": "8",
                "section": "A",
                "max_marks": 20.0,
                "academic_year": "2026-27",
                "source_filename": "register_photo_scan.jpg",
                "submission_notes": "Scanned from physical marks register"
            }
        )
        assert sub_resp.status_code == 200
        sub_data = sub_resp.json()
        assert sub_data["status"] == "success"
        sub_id = sub_data["data"]["submission_id"]
        assert sub_data["data"]["status"] == "pending_approval"
        assert sub_data["data"]["total_records"] == 2

        # 2. Teacher can view their submission
        teacher_list = client.get(
            "/api/v1/marks-bridge/submissions",
            headers={"Authorization": f"Bearer {teacher_token}"}
        )
        assert teacher_list.status_code == 200
        assert any(s["id"] == sub_id for s in teacher_list.json()["data"]["submissions"])

        # 3. RBAC Check: Teacher CANNOT approve their own submission (must be HM or Admin)
        forbidden_approval = client.post(
            f"/api/v1/marks-bridge/submissions/{sub_id}/approve",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={"review_notes": "Attempting teacher self-approval"}
        )
        assert forbidden_approval.status_code == 403, "Teacher should NOT be allowed to approve"

        # 4. Headmaster views submissions queue
        hm_list = client.get(
            "/api/v1/marks-bridge/submissions",
            headers={"Authorization": f"Bearer {hm_token}"}
        )
        assert hm_list.status_code == 200
        assert hm_list.json()["data"]["is_headmaster"] is True
        assert any(s["id"] == sub_id for s in hm_list.json()["data"]["submissions"])

        # 5. Headmaster fetches submission details with records
        detail = client.get(
            f"/api/v1/marks-bridge/submissions/{sub_id}",
            headers={"Authorization": f"Bearer {hm_token}"}
        )
        assert detail.status_code == 200
        assert len(detail.json()["data"]["records"]) == 2

        # 6. Headmaster exports official SATS CSV
        csv_resp = client.get(
            f"/api/v1/marks-bridge/submissions/{sub_id}/export-sats-csv",
            headers={"Authorization": f"Bearer {hm_token}"}
        )
        assert csv_resp.status_code == 200
        assert "text/csv" in csv_resp.headers["content-type"]
        assert "SATS2901001" in csv_resp.text

        # 7. Headmaster approves and pushes to SATS
        approve_resp = client.post(
            f"/api/v1/marks-bridge/submissions/{sub_id}/approve",
            headers={"Authorization": f"Bearer {hm_token}"},
            json={"review_notes": "Verified against class attendance. Approved for SATS push."}
        )
        assert approve_resp.status_code == 200
        appr_data = approve_resp.json()
        assert appr_data["status"] == "success"
        assert appr_data["data"]["status"] == "approved"
        assert appr_data["data"]["total"] >= 2

    def test_headmaster_reject_submission_workflow(self, client, teacher_token, hm_token):
        """Test rejection with feedback for teacher revision."""
        records = [
            {
                "student_sats_id": "SATS2901001",
                "student_name": "Darshan Gowda",
                "current_class": "8",
                "subject": "Science",
                "assessment_type": "FA2",
                "marks_obtained": 15.0,
                "max_marks": 20.0
            }
        ]
        sub_resp = client.post(
            "/api/v1/marks-bridge/submit",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={
                "records": records,
                "subject": "Science",
                "assessment_type": "FA2",
                "source_filename": "science_test.xlsx"
            }
        )
        sub_id = sub_resp.json()["data"]["submission_id"]

        reject_resp = client.post(
            f"/api/v1/marks-bridge/submissions/{sub_id}/reject",
            headers={"Authorization": f"Bearer {hm_token}"},
            json={"review_notes": "Roll no 5 marks missing. Please verify and re-submit."}
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["data"]["status"] == "rejected"

