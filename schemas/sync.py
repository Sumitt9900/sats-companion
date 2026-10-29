"""
schemas/sync.py — Pydantic v2 schemas for the offline-first sync engine.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SyncQueueItemOut(BaseModel):
    """Schema for a single sync queue entry (response)."""
    id: str
    operation: str
    entity_type: str
    entity_id: str
    checksum_sha256: str
    sync_status: str
    retry_count: int
    created_at: datetime
    synced_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class SyncStatusResponse(BaseModel):
    """Overall sync status response."""
    pending_count: int = Field(..., description="Number of records awaiting sync")
    conflict_count: int = Field(..., description="Number of records with sync conflicts")
    error_count: int = Field(..., description="Number of records that failed to sync")
    last_sync_at: Optional[datetime] = Field(None, description="Timestamp of last successful sync")
    last_sync_session_id: Optional[str] = None
    is_online: bool = Field(True, description="Whether the central SATS gateway is reachable")
    pending_items: List[SyncQueueItemOut] = Field(default_factory=list)


class SyncPushRequest(BaseModel):
    """Request body for pushing local changes to central."""
    device_id: Optional[str] = Field(None, description="Unique device identifier")
    force: bool = Field(False, description="Force re-sync already synced items")
    entity_types: Optional[List[str]] = Field(
        None, description="Filter to specific entity types (e.g. ['student', 'attendance'])"
    )


class SyncPushResponse(BaseModel):
    """Response from a sync push operation."""
    session_id: str
    pushed: int = 0
    synced: int = 0
    conflicts: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    conflict_items: List[Dict[str, Any]] = Field(default_factory=list)
    error_items: List[Dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class SyncPullResponse(BaseModel):
    """Response from a sync pull operation."""
    session_id: str
    pulled_count: int = 0
    updated_locally: int = 0
    message: str = ""
    pulled_since: Optional[datetime] = None


class ConflictResolutionRequest(BaseModel):
    """Request to resolve a specific sync conflict."""
    queue_item_id: str = Field(..., description="SyncQueue item ID with conflict")
    resolution: str = Field(..., description="'use_local' | 'use_server' | 'manual'")
    manual_payload: Optional[Dict[str, Any]] = Field(
        None, description="If resolution='manual', the merged payload"
    )


class ConflictResolutionResponse(BaseModel):
    """Response after conflict resolution."""
    queue_item_id: str
    resolution_applied: str
    message: str
