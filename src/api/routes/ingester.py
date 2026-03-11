"""
Ingester status API routes.
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from fastapi import APIRouter

router = APIRouter(prefix="/api/ingester", tags=["Ingester"])

SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv",
}


def _is_ignored(path: Path) -> bool:
    name = path.name
    lname = name.lower()

    if name.startswith("."):
        return True
    if lname.startswith("~$"):
        return True
    if "sync-conflict" in lname:
        return True
    if lname.endswith((".tmp", ".part", ".crdownload")):
        return True
    return False


def _count_pending_files(inbox_dir: Path) -> int:
    """Count ingestable media files waiting in inbox (excluding internal folders)."""
    if not inbox_dir.exists():
        return 0

    pending = 0
    for path in inbox_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.is_relative_to(inbox_dir / "_ingested"):
            continue
        if path.is_relative_to(inbox_dir / "_failed"):
            continue
        if _is_ignored(path):
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        pending += 1
    return pending


@router.get("/status")
async def ingester_status() -> Dict:
    """Return high-level Syncthing ingester health and queue metrics."""
    inbox_dir = Path(os.getenv("SYNC_INGEST_INBOX_DIR", "sync_inbox")).resolve()
    ingested_dir = Path(os.getenv("SYNC_INGEST_INGESTED_DIR", str(inbox_dir / "_ingested"))).resolve()
    failed_dir = Path(os.getenv("SYNC_INGEST_FAILED_DIR", str(inbox_dir / "_failed"))).resolve()
    state_db = Path(os.getenv("SYNC_INGEST_STATE_DB", "data/sync_ingest.db")).resolve()
    legacy_raw = os.getenv("SYNC_INGEST_LEGACY_DIRS", "").strip()
    legacy_dirs = [Path(p.strip()).resolve() for p in legacy_raw.split(",") if p.strip()]
    legacy_entries = []
    legacy_pending_total = 0
    for legacy_dir in legacy_dirs:
        pending = _count_pending_files(legacy_dir)
        legacy_pending_total += pending
        legacy_entries.append(
            {
                "path": str(legacy_dir),
                "exists": legacy_dir.exists(),
                "pending_files": pending,
            }
        )

    response = {
        "configured": True,
        "inbox_dir": str(inbox_dir),
        "state_db": str(state_db),
        "legacy_dirs": legacy_entries,
        "paths": {
            "inbox_exists": inbox_dir.exists(),
            "ingested_exists": ingested_dir.exists(),
            "failed_exists": failed_dir.exists(),
            "state_db_exists": state_db.exists(),
        },
        "counts": {
            "pending_files": _count_pending_files(inbox_dir) + legacy_pending_total,
            "ingested_files": 0,
            "failed_files": 0,
        },
        "last_ingested_at": None,
        "last_ingested_profile": None,
    }

    if ingested_dir.exists():
        response["counts"]["ingested_files"] = sum(1 for p in ingested_dir.rglob("*") if p.is_file())
    if failed_dir.exists():
        response["counts"]["failed_files"] = sum(1 for p in failed_dir.rglob("*") if p.is_file())

    if not state_db.exists():
        return response

    try:
        conn = sqlite3.connect(state_db)
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   MAX(ingested_at) AS last_ingested_at
            FROM ingested_files
            """
        ).fetchone()
        latest = conn.execute(
            """
            SELECT profile_id, ingested_at
            FROM ingested_files
            ORDER BY ingested_at DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()

    response["counts"]["ingested_files"] = int(row[0] or 0)
    response["last_ingested_at"] = row[1]
    if latest:
        response["last_ingested_profile"] = latest[0]
        response["last_ingested_at"] = latest[1]

    # Convenience status for dashboard
    has_input_source = response["paths"]["inbox_exists"] or any(item["exists"] for item in legacy_entries)
    response["healthy"] = response["paths"]["state_db_exists"] and has_input_source
    response["checked_at"] = datetime.now(timezone.utc).isoformat()

    return response
