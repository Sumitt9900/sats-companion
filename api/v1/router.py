"""
api/v1/router.py — Aggregates all v1 API routers.

All routers are included here and then registered in main.py under /api/v1.
"""
from fastapi import APIRouter

from api.v1.auth import router as auth_router
from api.v1.schools import router as schools_router
from api.v1.teachers import router as teachers_router
from api.v1.students import router as students_router
from api.v1.attendance import router as attendance_router
from api.v1.assessments import router as assessments_router
from api.v1.tc import router as tc_router
from api.v1.ai_insights import router as ai_router
from api.v1.sync import router as sync_router

# Main v1 router — all sub-routers are mounted here
v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(schools_router)
v1_router.include_router(teachers_router)
v1_router.include_router(students_router)
v1_router.include_router(attendance_router)
v1_router.include_router(assessments_router)
v1_router.include_router(tc_router)
v1_router.include_router(ai_router)
v1_router.include_router(sync_router)
