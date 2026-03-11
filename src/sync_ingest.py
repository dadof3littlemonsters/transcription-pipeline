"""Syncthing inbox ingester.

Watches a synced inbox directory, validates stable media files, and submits them
as jobs to the API. Files are moved to _ingested/ or _failed/ after handling.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, List, Tuple

import requests
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("sync-ingest")


SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv",
}


@dataclass
class IngestConfig:
    inbox_dir: Path
    ingested_dir: Path
    failed_dir: Path
    legacy_dirs: List[Path]
    state_db: Path
    api_base_url: str
    api_key: str
    poll_seconds: int
    stable_seconds: int
    max_file_size_mb: int
    folder_map: Dict[str, str]


def parse_folder_map(raw: str) -> Dict[str, str]:
    """Parse mapping like 'kate:social_work_lecture,keira:business_lecture'."""
    default = {
        "meeting": "meeting",
        "supervision": "supervision",
        "client": "client",
        "braindump": "braindump",
        "lecture": "lecture",
        "kate": "social_work_lecture",
        "keira": "business_lecture",
    }
    if not raw.strip():
        return default

    parsed: Dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            logger.warning("Skipping invalid folder map entry (expected key:value): %s", item)
            continue
        key, value = item.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key or not value:
            continue
        parsed[key] = value

    for k, v in default.items():
        parsed.setdefault(k, v)
    return parsed


def load_config() -> IngestConfig:
    inbox_dir = Path(os.getenv("SYNC_INGEST_INBOX_DIR", "sync_inbox")).resolve()
    ingested_dir = Path(os.getenv("SYNC_INGEST_INGESTED_DIR", str(inbox_dir / "_ingested"))).resolve()
    failed_dir = Path(os.getenv("SYNC_INGEST_FAILED_DIR", str(inbox_dir / "_failed"))).resolve()
    state_db = Path(os.getenv("SYNC_INGEST_STATE_DB", "data/sync_ingest.db")).resolve()
    legacy_raw = os.getenv("SYNC_INGEST_LEGACY_DIRS", "").strip()
    legacy_dirs = [Path(p.strip()).resolve() for p in legacy_raw.split(",") if p.strip()]

    cfg = IngestConfig(
        inbox_dir=inbox_dir,
        ingested_dir=ingested_dir,
        failed_dir=failed_dir,
        legacy_dirs=legacy_dirs,
        state_db=state_db,
        api_base_url=os.getenv("SYNC_INGEST_API_BASE_URL", "http://app:8000").rstrip("/"),
        api_key=os.getenv("PIPELINE_API_KEY", ""),
        poll_seconds=int(os.getenv("SYNC_INGEST_POLL_SECONDS", "10")),
        stable_seconds=int(os.getenv("SYNC_INGEST_STABLE_SECONDS", "8")),
        max_file_size_mb=int(os.getenv("SYNC_INGEST_MAX_FILE_SIZE_MB", "500")),
        folder_map=parse_folder_map(os.getenv("SYNC_INGEST_FOLDER_MAP", "")),
    )

    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.ingested_dir.mkdir(parents=True, exist_ok=True)
    cfg.failed_dir.mkdir(parents=True, exist_ok=True)
    cfg.state_db.parent.mkdir(parents=True, exist_ok=True)
    for legacy_dir in cfg.legacy_dirs:
        legacy_dir.mkdir(parents=True, exist_ok=True)

    return cfg


def init_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ingested_files (
                sha256 TEXT PRIMARY KEY,
                src_rel_path TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                job_id TEXT,
                ingested_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_supported_media(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def is_ignored(path: Path) -> bool:
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


def resolve_profile_id(
    path: Path,
    root_dir: Path,
    folder_map: Dict[str, str],
    source_label: Optional[str] = None,
) -> Optional[str]:
    """Resolve profile from path segments, with optional source-label fallback."""
    try:
        rel = path.relative_to(root_dir)
    except ValueError:
        return None

    for segment in rel.parts[:-1]:
        key = segment.lower()
        if key in folder_map:
            return folder_map[key]
    if source_label:
        return folder_map.get(source_label.lower())
    return None


def is_stable(path: Path, stable_seconds: int) -> bool:
    if not path.exists() or not path.is_file():
        return False

    first_size = path.stat().st_size
    if first_size <= 0:
        return False

    time.sleep(stable_seconds)

    if not path.exists() or not path.is_file():
        return False

    second_size = path.stat().st_size
    return first_size == second_size and second_size > 0


def already_ingested(db_path: Path, sha256: str) -> bool:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM ingested_files WHERE sha256 = ? LIMIT 1", (sha256,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def record_ingested(
    db_path: Path,
    sha256: str,
    src_rel_path: str,
    profile_id: str,
    job_id: Optional[str],
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO ingested_files
            (sha256, src_rel_path, profile_id, job_id, ingested_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (sha256, src_rel_path, profile_id, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def move_preserving_rel(src: Path, base_dir: Path, target_root: Path) -> Path:
    rel = src.relative_to(base_dir)
    dest = target_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Avoid collision if file name already exists
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        timestamp = int(time.time())
        dest = dest.with_name(f"{stem}_{timestamp}{suffix}")

    shutil.move(str(src), str(dest))
    return dest


def submit_job(cfg: IngestConfig, file_path: Path, profile_id: str) -> Dict:
    url = f"{cfg.api_base_url}/api/jobs"
    headers = {}
    if cfg.api_key:
        headers["x-api-key"] = cfg.api_key

    with open(file_path, "rb") as fh:
        files = {"file": (file_path.name, fh, "application/octet-stream")}
        data = {"profile_id": profile_id}
        resp = requests.post(url, files=files, data=data, headers=headers, timeout=120)

    if resp.status_code >= 400:
        raise RuntimeError(f"API {resp.status_code}: {resp.text[:500]}")

    return resp.json()


def iter_candidate_files(
    root_dir: Path,
    ingested_dir: Optional[Path],
    failed_dir: Optional[Path],
):
    for path in sorted(root_dir.rglob("*")):
        if not path.is_file():
            continue
        if ingested_dir is not None and path.is_relative_to(ingested_dir):
            continue
        if failed_dir is not None and path.is_relative_to(failed_dir):
            continue
        yield path


def _process_source(
    cfg: IngestConfig,
    source_root: Path,
    source_ingested: Optional[Path],
    source_failed: Optional[Path],
    move_files: bool = True,
    source_label: Optional[str] = None,
) -> int:
    processed = 0
    for path in iter_candidate_files(source_root, source_ingested, source_failed):
        if is_ignored(path):
            continue
        if not is_supported_media(path):
            continue

        profile_id = resolve_profile_id(path, source_root, cfg.folder_map, source_label=source_label)
        if not profile_id:
            logger.warning("No folder map match for file: %s", path)
            continue

        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > cfg.max_file_size_mb:
            logger.error("File exceeds max size (%.1fMB > %dMB): %s", size_mb, cfg.max_file_size_mb, path)
            if move_files and source_failed is not None:
                move_preserving_rel(path, source_root, source_failed)
            processed += 1
            continue

        if not is_stable(path, cfg.stable_seconds):
            logger.info("File not stable yet, will retry: %s", path)
            continue

        try:
            sha256 = file_sha256(path)
        except Exception as exc:
            logger.exception("Failed hashing file %s: %s", path, exc)
            continue

        if already_ingested(cfg.state_db, sha256):
            logger.info("Duplicate file (already ingested), archiving: %s", path)
            if move_files and source_ingested is not None:
                move_preserving_rel(path, source_root, source_ingested)
            processed += 1
            continue

        rel = str(path.relative_to(source_root))
        try:
            logger.info("Submitting job for %s as profile %s", rel, profile_id)
            job = submit_job(cfg, path, profile_id)
            job_id = job.get("id")
            record_ingested(cfg.state_db, sha256, rel, profile_id, job_id)
            if move_files and source_ingested is not None:
                moved = move_preserving_rel(path, source_root, source_ingested)
                logger.info("Queued job %s and archived source to %s", job_id, moved)
            else:
                logger.info("Queued job %s from legacy source (file left in place): %s", job_id, path)
            processed += 1
        except Exception as exc:
            logger.exception("Failed to submit %s: %s", path, exc)
            try:
                if move_files and source_failed is not None:
                    moved = move_preserving_rel(path, source_root, source_failed)
                    logger.error("Moved failed file to %s", moved)
            except Exception as move_exc:
                logger.exception("Failed moving errored file %s: %s", path, move_exc)
            processed += 1

    return processed


def run_once(cfg: IngestConfig) -> int:
    processed = _process_source(
        cfg=cfg,
        source_root=cfg.inbox_dir,
        source_ingested=cfg.ingested_dir,
        source_failed=cfg.failed_dir,
        source_label=None,
    )

    for legacy_dir in cfg.legacy_dirs:
        processed += _process_source(
            cfg=cfg,
            source_root=legacy_dir,
            source_ingested=None,
            source_failed=None,
            move_files=False,
            source_label=legacy_dir.name,
        )

    return processed


def main() -> None:
    cfg = load_config()
    init_db(cfg.state_db)

    logger.info("Syncthing ingester started")
    logger.info("Inbox: %s", cfg.inbox_dir)
    logger.info("Ingested: %s", cfg.ingested_dir)
    logger.info("Failed: %s", cfg.failed_dir)
    if cfg.legacy_dirs:
        logger.info("Legacy dirs: %s", ", ".join(str(p) for p in cfg.legacy_dirs))
    logger.info("API: %s", cfg.api_base_url)
    logger.info("Folder map: %s", json.dumps(cfg.folder_map, indent=2))

    while True:
        try:
            count = run_once(cfg)
            if count:
                logger.info("Cycle complete, handled %d file(s)", count)
        except Exception as exc:
            logger.exception("Ingest cycle failed: %s", exc)
        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    main()
