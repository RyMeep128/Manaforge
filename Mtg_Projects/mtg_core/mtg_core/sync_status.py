"""Stable bulk-download checkpoint values, separate from image status."""
from enum import StrEnum


class SyncStatus(StrEnum):
    IDLE = "idle"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"


def normalize_sync_status(value: str) -> SyncStatus | str:
    """Type known values while preserving unrecognized checkpoint strings."""
    try:
        return SyncStatus(value)
    except ValueError:
        return value
