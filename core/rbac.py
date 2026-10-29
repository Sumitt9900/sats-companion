"""
core/rbac.py — Role-Based Access Control (RBAC) for SATS Companion.

Roles (highest to lowest privilege):
  ADMIN       → Full access to all operations.
  HEADMASTER  → School-level admin; can approve TCs, manage all teachers/students in school.
  TEACHER     → Can mark attendance, record assessments for own class; can view students.
  DATA_ENTRY  → Read-only + bulk import; cannot approve TCs or delete records.

Usage:
    from core.rbac import require_role
    from core.models import UserRole

    @router.delete("/{sats_id}")
    def delete_student(..., teacher=Depends(require_role(UserRole.HEADMASTER))):
        ...
"""
from typing import List
from fastapi import Depends, HTTPException, status

from core.models import UserRole
from core.security import get_current_teacher


def require_role(*allowed_roles: UserRole):
    """
    FastAPI dependency factory that enforces role-based access.

    Args:
        *allowed_roles: One or more UserRole values that are permitted to call the endpoint.

    Returns:
        A FastAPI dependency function.

    Example:
        @router.post("/approve", dependencies=[Depends(require_role(UserRole.HEADMASTER, UserRole.ADMIN))])
    """
    def _check(teacher=Depends(get_current_teacher)):
        teacher_role = getattr(teacher, "role", UserRole.TEACHER)
        # ADMIN always has access
        if teacher_role == UserRole.ADMIN:
            return teacher
        if teacher_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient privileges. Required role: "
                    f"{' or '.join(r.value for r in allowed_roles)}. "
                    f"Your role: {teacher_role.value}."
                ),
            )
        return teacher
    return _check


def require_headmaster_or_admin(teacher=Depends(get_current_teacher)):
    """Shortcut dependency: allows HEADMASTER and ADMIN."""
    return require_role(UserRole.HEADMASTER, UserRole.ADMIN)(teacher)


def require_admin(teacher=Depends(get_current_teacher)):
    """Shortcut dependency: allows only ADMIN."""
    return require_role(UserRole.ADMIN)(teacher)
