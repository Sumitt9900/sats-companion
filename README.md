# SATS-Companion Micro-ERP

Offline-first middleware and micro-ERP system designed for rural Karnataka government and aided schools to interface with the Karnataka **SATS (Student Achievement Tracking System)** portal.

---

## 🌟 Key Features

- **Offline-First Architecture**: Local transactions with a cryptographic sync queue (`SHA-256` payload verification) and conflict resolution.
- **Teacher & School Management**: KGID employee authentication, designation tracking, and DISE school profiles.
- **Student Information System**: Comprehensive student profile tracking with caste categories, attendance, and masked/encrypted Aadhaar fields.
- **Attendance & Assessments**: Bulk daily attendance recording, FA1-FA4 / SA1-SA2 examinations, and chapter-level performance analysis.
- **Transfer Certificates (TC)**: Complete digital workflow for school-to-school student transfers.
- **AI Educational Insights**: Powered by Google Gemini (`google-genai`), generating Karnataka-specific student reports, remedial recommendations, and attendance interventions.
- **Role-Based Access Control (RBAC)**: Support for Headmaster (HM), Teacher, Data Entry, and Admin permissions.

---

## 🏗️ Architecture & Project Structure

```
sats-companion/
├── main.py                     # FastAPI application entry point & CORS
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variables template
├── core/
│   ├── config.py               # Pydantic v2 settings management
│   ├── databsae.py             # SQLAlchemy session & database engine
│   ├── models.py               # ORM entities (School, Teacher, Student, Attendance, Assessment, TC, SyncQueue, SyncLog)
│   ├── security.py             # JWT token handling & password hashing
│   ├── rbac.py                 # Role-based access control dependencies
│   └── encryption.py           # Fernet encryption for sensitive PII
├── schemas/                    # Pydantic v2 data validation schemas
│   ├── auth.py, school.py, teacher.py, student.py
│   ├── attendance.py, assessment.py, tc.py, sync.py
├── services/
│   ├── ai_service.py           # Google Gemini AI integrations
│   ├── sats_service.py         # Academic & attendance analytics
│   └── sync_service.py         # Offline queue & conflict resolution engine
└── api/v1/                     # Versioned REST endpoints
    ├── auth.py, schools.py, teachers.py, students.py
    ├── attendance.py, assessments.py, tc.py, ai_insights.py, sync.py
    └── router.py               # Aggregate v1 router
```

---

## 🚀 Quick Start

### 1. Clone & Setup Virtual Environment

```bash
git clone https://github.com/<your-username>/sats-companion.git
cd sats-companion

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials and Gemini API key
```

### 3. Run the Server

```bash
uvicorn main:app --reload --port 8000
```

- **Interactive API Documentation (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative Documentation (ReDoc)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 📡 Sync Engine Overview

1. **Local Mutation**: Actions (e.g. marking attendance) are committed locally.
2. **Sync Queue**: Mutations are saved to `sync_queue` with deterministic `SHA-256` checksums.
3. **Synchronization**: When internet connectivity is available, the client triggers `POST /api/v1/sync/push` to push local batches and resolve conflicts.

