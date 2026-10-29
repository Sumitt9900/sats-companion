"""
scripts/seed_data.py — Seed demo data for SATS Companion.

Populates:
  - 1 Karnataka Government High School (DISE: 29210101001)
  - 1 Headmaster (KGID: KGID10001, Pass: admin@123)
  - 1 Assistant Teacher (KGID: KGID10002, Pass: teacher@123)
  - 10 Students in Class 8 and 7
  - Initial attendance & assessment records

Usage:
  python scripts/seed_data.py
"""
import sys
import os
from datetime import date, timedelta
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.databsae import SessionLocal, Base, engine
from core.models import (
    School, Teacher, Student, Attendance, Assessment,
    SchoolType, Gender, CasteCategory, Designation, UserRole,
    AttendanceStatus, AssessmentType
)
from core.security import hash_password

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. School
        dise = "29210101001"
        school = db.query(School).filter(School.dise_code == dise).first()
        if not school:
            school = School(
                dise_code=dise,
                name="Government High School, Channapatna",
                district="Ramanagara",
                taluk="Channapatna",
                block="Channapatna Rural",
                village="Mangalwarpet",
                address="Near Bus Stand, BM Road, Channapatna - 562160",
                pincode="562160",
                school_type=SchoolType.GOVERNMENT,
                medium="Kannada",
                category="High School (6-10)",
                phone="080-27251000",
                email="ghs.channapatna@karnataka.gov.in",
            )
            db.add(school)
            db.commit()
            print(f"✅ School created: {school.name} (DISE: {dise})")

        # 2. Headmaster
        hm = db.query(Teacher).filter(Teacher.kgid == "KGID10001").first()
        if not hm:
            hm = Teacher(
                id=str(uuid.uuid4()),
                kgid="KGID10001",
                name="Siddaramaiah K",
                designation=Designation.HM,
                subject="Social Science",
                school_dise_code=dise,
                phone="9845011111",
                email="hm.channapatna@gmail.com",
                hashed_password=hash_password("admin@123"),
                is_admin=True,
                role=UserRole.HEADMASTER,
            )
            db.add(hm)
            db.commit()
            print("✅ Headmaster created: KGID10001 (Password: admin@123)")

        # 3. Teacher
        teacher = db.query(Teacher).filter(Teacher.kgid == "KGID10002").first()
        if not teacher:
            teacher = Teacher(
                id=str(uuid.uuid4()),
                kgid="KGID10002",
                name="Suma Ramesh",
                designation=Designation.ASST_TEACHER,
                subject="Mathematics & Science",
                school_dise_code=dise,
                phone="9845022222",
                email="suma.teacher@gmail.com",
                hashed_password=hash_password("teacher@123"),
                is_admin=False,
                role=UserRole.TEACHER,
            )
            db.add(teacher)
            db.commit()
            print("✅ Teacher created: KGID10002 (Password: teacher@123)")

        # 4. Students
        demo_students = [
            ("SATS2901001", "Darshan Gowda", "male", "8", "A", CasteCategory.OBC),
            ("SATS2901002", "Aishwarya M", "female", "8", "A", CasteCategory.GENERAL),
            ("SATS2901003", "Kiran Kumar", "male", "8", "A", CasteCategory.SC),
            ("SATS2901004", "Lakshmi Bai", "female", "8", "A", CasteCategory.ST),
            ("SATS2901005", "Mohammed Farooq", "male", "8", "A", CasteCategory.OBC),
            ("SATS2901006", "Sneha Patil", "female", "7", "B", CasteCategory.GENERAL),
            ("SATS2901007", "Basavaraj H", "male", "7", "B", CasteCategory.OBC),
            ("SATS2901008", "Megha N", "female", "7", "B", CasteCategory.SC),
            ("SATS2901009", "Prajwal Shastry", "male", "7", "B", CasteCategory.GENERAL),
            ("SATS2901010", "Radha Krishna", "female", "7", "B", CasteCategory.OBC),
        ]

        added_count = 0
        for sats_id, name, gender, current_class, section, caste in demo_students:
            exists = db.query(Student).filter(Student.sats_id == sats_id).first()
            if not exists:
                s = Student(
                    sats_id=sats_id,
                    name=name,
                    dob=date(2011, 5, 15),
                    gender=Gender(gender),
                    current_class=current_class,
                    section=section,
                    school_dise_code=dise,
                    caste_category=caste,
                    father_name=f"Father of {name}",
                    mother_name=f"Mother of {name}",
                    is_active=True,
                )
                db.add(s)
                added_count += 1
        db.commit()
        if added_count > 0:
            print(f"✅ Enrolled {added_count} sample students.")

        # 5. Sample Attendance for past 3 days
        today = date.today()
        for i in range(3):
            att_day = today - timedelta(days=i)
            for sats_id, _, _, _, _, _ in demo_students[:5]:
                existing_att = db.query(Attendance).filter(
                    Attendance.student_sats_id == sats_id,
                    Attendance.attendance_date == att_day,
                ).first()
                if not existing_att:
                    att = Attendance(
                        id=str(uuid.uuid4()),
                        student_sats_id=sats_id,
                        attendance_date=att_day,
                        status=AttendanceStatus.PRESENT if (i != 1 or sats_id != "SATS2901003") else AttendanceStatus.ABSENT,
                        marked_by_teacher_id=teacher.id,
                    )
                    db.add(att)
        db.commit()
        print("✅ Seeded initial attendance records.")

        print("\n🎉 Seeding successfully completed!")
        print("Login credentials to test in UI:")
        print("  - Headmaster: KGID10001 / admin@123")
        print("  - Teacher:    KGID10002 / teacher@123")

    except Exception as e:
        db.rollback()
        print(f"❌ Seeding error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
