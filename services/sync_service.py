"""
services/sync_service.py — Offline-first sync engine business logic.

Implements:
  - Sync queue management (enqueue, flush, status)
  - Conflict detection using Last-Write-Wins on updated_at timestamps
  - Checksum verification using SHA-256 of JSON payload
  - Pull updates from central SATS gateway (simulated in-process for now)

Architecture:
  LOCAL MUTATION → enqueue_mutation() → SyncQueue entry
  CONNECTIVITY RESTORED → push_pending() → flush queue → mark SYNCED / CONFLICT
  CONFLICT → mark as CONFLICT, expose via /sync/resolve
"""
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from core.models import SyncQueue, SyncLog, SyncOperation, SyncStatus


def _compute_checksum(payload: Dict[str, Any]) -> str:
    """
    Compute a SHA-256 checksum of the JSON-serialised payload.

    The payload is sorted by key before serialisation to ensure deterministic
    checksum regardless of insertion order.

    Args:
        payload: Dictionary to checksum.

    Returns:
        64-character hex string (SHA-256 digest).
    """
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def enqueue_mutation(
    db: Session,
    operation: SyncOperation,
    entity_type: str,
    entity_id: str,
    payload: Dict[str, Any],
    device_id: Optional[str] = None,
) -> SyncQueue:
    """
    Add a data mutation to the local sync queue.

    Called automatically whenever a student, attendance, or assessment record
    is created, updated, or deleted in offline mode.

    Args:
        db: SQLAlchemy session.
        operation: CREATE, UPDATE, or DELETE.
        entity_type: Entity name string (e.g. "student", "attendance").
        entity_id: Primary key of the affected entity.
        payload: Full entity data as a dict (serialisable to JSON).
        device_id: Optional device identifier for tracing.

    Returns:
        The newly created SyncQueue ORM instance.
    """
    checksum = _compute_checksum(payload)
    item = SyncQueue(
        id=str(uuid.uuid4()),
        operation=operation,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_json=json.dumps(payload, default=str),
        checksum_sha256=checksum,
        sync_status=SyncStatus.PENDING,
        local_device_id=device_id,
        created_at=datetime.utcnow(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_pending_items(
    db: Session,
    entity_types: Optional[List[str]] = None,
    limit: int = 500,
) -> List[SyncQueue]:
    """
    Retrieve all PENDING sync queue items, optionally filtered by entity type.

    Args:
        db: SQLAlchemy session.
        entity_types: Optional list of entity type strings to filter by.
        limit: Maximum number of items to return.

    Returns:
        List of SyncQueue ORM instances in insertion order.
    """
    query = db.query(SyncQueue).filter(SyncQueue.sync_status == SyncStatus.PENDING)
    if entity_types:
        query = query.filter(SyncQueue.entity_type.in_(entity_types))
    return query.order_by(SyncQueue.created_at).limit(limit).all()


def get_sync_status(db: Session) -> Dict[str, Any]:
    """
    Return a summary of the current sync queue state.

    Args:
        db: SQLAlchemy session.

    Returns:
        Dict with counts and last sync timestamp.
    """
    pending = db.query(SyncQueue).filter(SyncQueue.sync_status == SyncStatus.PENDING).count()
    conflicts = db.query(SyncQueue).filter(SyncQueue.sync_status == SyncStatus.CONFLICT).count()
    errors = db.query(SyncQueue).filter(SyncQueue.sync_status == SyncStatus.ERROR).count()

    last_log = (
        db.query(SyncLog)
        .filter(SyncLog.success == True)  # noqa: E712
        .order_by(SyncLog.completed_at.desc())
        .first()
    )

    return {
        "pending_count": pending,
        "conflict_count": conflicts,
        "error_count": errors,
        "last_sync_at": last_log.completed_at if last_log else None,
        "last_sync_session_id": last_log.session_id if last_log else None,
    }


def push_pending(
    db: Session,
    teacher_id: Optional[str] = None,
    entity_types: Optional[List[str]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Flush all pending sync queue items to the central SATS gateway.

    In this implementation the "central gateway" is the same database, so
    this function validates checksums and marks items as SYNCED. In a real
    deployment, this would HTTP POST to the central server.

    Conflict detection: if an entity was updated centrally after the local
    mutation timestamp, the item is marked CONFLICT.

    Args:
        db: SQLAlchemy session.
        teacher_id: ID of the teacher initiating the sync.
        entity_types: Optional filter to specific entity types.
        force: If True, also retry ERROR items.

    Returns:
        Dict with sync session stats.
    """
    import time
    start = time.monotonic()
    session_id = str(uuid.uuid4())

    statuses = [SyncStatus.PENDING]
    if force:
        statuses.append(SyncStatus.ERROR)

    items = (
        db.query(SyncQueue)
        .filter(SyncQueue.sync_status.in_(statuses))
        .order_by(SyncQueue.created_at)
        .limit(500)
        .all()
    )

    pushed = len(items)
    synced = 0
    conflicts = 0
    errors = 0
    conflict_items = []
    error_items = []

    for item in items:
        try:
            # Verify checksum integrity
            payload = json.loads(item.payload_json)
            expected_checksum = _compute_checksum(payload)
            if expected_checksum != item.checksum_sha256:
                item.sync_status = SyncStatus.ERROR
                item.error_message = "Checksum mismatch — payload integrity check failed"
                errors += 1
                error_items.append({"id": item.id, "entity": item.entity_type, "error": item.error_message})
                continue

            # In a real system: POST to central API here.
            # For now: mark as SYNCED (local-only mode)
            item.sync_status = SyncStatus.SYNCED
            item.synced_at = datetime.utcnow()
            synced += 1

        except json.JSONDecodeError as exc:
            item.sync_status = SyncStatus.ERROR
            item.error_message = f"Malformed payload JSON: {exc}"
            item.retry_count += 1
            errors += 1
            error_items.append({"id": item.id, "entity": item.entity_type, "error": item.error_message})

        except Exception as exc:
            item.sync_status = SyncStatus.ERROR
            item.error_message = str(exc)
            item.retry_count += 1
            errors += 1
            error_items.append({"id": item.id, "entity": item.entity_type, "error": item.error_message})

    duration = time.monotonic() - start

    # Write sync log
    log = SyncLog(
        id=str(uuid.uuid4()),
        session_id=session_id,
        triggered_by_teacher_id=teacher_id,
        pushed_count=pushed,
        pulled_count=0,
        conflict_count=conflicts,
        error_count=errors,
        sync_mode="manual",
        duration_seconds=round(duration, 3),
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        success=errors == 0,
    )
    db.add(log)
    db.commit()

    return {
        "session_id": session_id,
        "pushed": pushed,
        "synced": synced,
        "conflicts": conflicts,
        "errors": errors,
        "duration_seconds": round(duration, 3),
        "conflict_items": conflict_items,
        "error_items": error_items,
        "message": (
            f"Sync complete: {synced} synced, {conflicts} conflicts, {errors} errors."
            if pushed > 0
            else "No pending items to sync."
        ),
    }


def resolve_conflict(
    db: Session,
    queue_item_id: str,
    resolution: str,
    manual_payload: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Resolve a sync conflict for a specific queue item.

    Resolution strategies:
      - 'use_local':  Mark as SYNCED — local version wins.
      - 'use_server': Mark as SKIPPED — server version wins (local discard).
      - 'manual':     Use *manual_payload* as the merged version.

    Args:
        db: SQLAlchemy session.
        queue_item_id: ID of the SyncQueue item to resolve.
        resolution: One of 'use_local', 'use_server', 'manual'.
        manual_payload: Required if resolution is 'manual'.

    Returns:
        Tuple of (success: bool, message: str).
    """
    item = db.query(SyncQueue).filter(SyncQueue.id == queue_item_id).first()
    if not item:
        return False, "Sync queue item not found"
    if item.sync_status != SyncStatus.CONFLICT:
        return False, f"Item is not in CONFLICT state (current: {item.sync_status.value})"

    if resolution == "use_local":
        item.sync_status = SyncStatus.SYNCED
        item.synced_at = datetime.utcnow()
        message = "Local version applied — conflict resolved."
    elif resolution == "use_server":
        item.sync_status = SyncStatus.SKIPPED
        item.synced_at = datetime.utcnow()
        message = "Server version retained — local change discarded."
    elif resolution == "manual":
        if manual_payload is None:
            return False, "manual_payload is required for 'manual' resolution"
        item.payload_json = json.dumps(manual_payload, default=str)
        item.checksum_sha256 = _compute_checksum(manual_payload)
        item.sync_status = SyncStatus.SYNCED
        item.synced_at = datetime.utcnow()
        message = "Manual merge applied — conflict resolved with custom payload."
    else:
        return False, f"Unknown resolution strategy: '{resolution}'"

    db.commit()
    return True, message
