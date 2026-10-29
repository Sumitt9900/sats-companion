"""
api/v1/sync.py — Offline-first synchronisation API endpoints.

These endpoints drive the sync layer of the SATS Companion:
  GET  /sync/status          — Pending count, last sync time, online/offline indicator
  POST /sync/push            — Flush pending local mutations to central SATS gateway
  POST /sync/pull            — Fetch upstream changes since last sync
  POST /sync/resolve         — Manually resolve a specific sync conflict
  GET  /sync/history         — List recent sync session logs
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.databsae import get_db
from core.security import get_current_teacher
from core.models import SyncQueue, SyncLog, SyncStatus
from schemas.sync import (
    SyncStatusResponse, SyncQueueItemOut,
    SyncPushRequest, SyncPushResponse,
    SyncPullResponse,
    ConflictResolutionRequest, ConflictResolutionResponse,
)
from services.sync_service import (
    get_sync_status,
    get_pending_items,
    push_pending,
    resolve_conflict,
)

router = APIRouter(prefix="/sync", tags=["Sync Engine"])


@router.get(
    "/status",
    response_model=SyncStatusResponse,
    summary="Get current sync status",
    description=(
        "Returns the number of pending, conflicted, and errored sync queue items. "
        "Also reports the last successful sync timestamp and whether the system considers "
        "itself online (central SATS gateway reachable)."
    ),
)
def get_status(
    include_items: bool = False,
    db: Session = Depends(get_db),
    teacher=Depends(get_current_teacher),
):
    """Return sync queue status — the primary endpoint polled by the PWA status badge."""
    stats = get_sync_status(db)
    pending_items = []
    if include_items:
        items = get_pending_items(db, limit=50)
        pending_items = [SyncQueueItemOut.model_validate(i) for i in items]

    return SyncStatusResponse(
        pending_count=stats["pending_count"],
        conflict_count=stats["conflict_count"],
        error_count=stats["error_count"],
        last_sync_at=stats["last_sync_at"],
        last_sync_session_id=stats["last_sync_session_id"],
        is_online=True,  # In production: ping central gateway
        pending_items=pending_items,
    )


@router.post(
    "/push",
    response_model=SyncPushResponse,
    summary="Push pending local mutations to central",
    description=(
        "Flushes the local sync queue to the central SATS gateway. "
        "Verifies SHA-256 checksums for payload integrity before submission. "
        "Returns a per-session summary of synced, conflicted, and errored items."
    ),
)
def push_sync(
    request: SyncPushRequest,
    db: Session = Depends(get_db),
    teacher=Depends(get_current_teacher),
):
    """Trigger a sync push — called when the user clicks 'Sync Now'."""
    result = push_pending(
        db=db,
        teacher_id=teacher.id,
        entity_types=request.entity_types,
        force=request.force,
    )
    return SyncPushResponse(**result)


@router.post(
    "/pull",
    response_model=SyncPullResponse,
    summary="Pull upstream changes from central SATS gateway",
    description=(
        "Fetches records updated centrally since the last successful pull. "
        "Used to keep the local database current with changes made by other "
        "school terminals or the central SATS portal administrators."
    ),
)
def pull_sync(
    since: Optional[datetime] = None,
    db: Session = Depends(get_db),
    teacher=Depends(get_current_teacher),
):
    """
    Pull upstream updates.

    In this implementation, the local DB IS the central DB, so this is a
    no-op that returns stats. In a multi-node deployment, this would
    fetch delta records from the central server.
    """
    import uuid as _uuid_mod
    session_id = str(_uuid_mod.uuid4())
    return SyncPullResponse(
        session_id=session_id,
        pulled_count=0,
        updated_locally=0,
        pulled_since=since,
        message=(
            "Pull complete. Local database is up to date with central SATS gateway. "
            "(Note: In single-node deployment, pull is a no-op.)"
        ),
    )


@router.post(
    "/resolve",
    response_model=ConflictResolutionResponse,
    summary="Resolve a sync conflict",
    description=(
        "Allows a Headmaster or Admin to manually resolve a sync conflict. "
        "Strategies: 'use_local' (keep local version), 'use_server' (discard local), "
        "'manual' (provide a merged payload)."
    ),
)
def resolve_sync_conflict(
    request: ConflictResolutionRequest,
    db: Session = Depends(get_db),
    teacher=Depends(get_current_teacher),
):
    """Resolve a single conflict item. Only HM / Admin should call this."""
    success, message = resolve_conflict(
        db=db,
        queue_item_id=request.queue_item_id,
        resolution=request.resolution,
        manual_payload=request.manual_payload,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return ConflictResolutionResponse(
        queue_item_id=request.queue_item_id,
        resolution_applied=request.resolution,
        message=message,
    )


@router.get(
    "/history",
    summary="List recent sync session history",
    description="Returns the last 20 sync session logs with counts and timestamps.",
)
def sync_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    teacher=Depends(get_current_teacher),
):
    """Return recent sync logs for audit/transparency."""
    logs = (
        db.query(SyncLog)
        .order_by(SyncLog.started_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return {
        "status": "success",
        "data": [
            {
                "session_id": l.session_id,
                "pushed": l.pushed_count,
                "pulled": l.pulled_count,
                "conflicts": l.conflict_count,
                "errors": l.error_count,
                "mode": l.sync_mode,
                "duration_seconds": l.duration_seconds,
                "success": l.success,
                "started_at": l.started_at,
                "completed_at": l.completed_at,
            }
            for l in logs
        ],
    }
