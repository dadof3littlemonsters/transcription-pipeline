"""
Job management API routes.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, Request, status, Query
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func
from sqlmodel import Session, select

from src.api.models import Job, StageResult
from src.api.schemas import JobCreateRequest, JobResponse, JobListResponse, StageResultResponse
from src.api.dependencies import get_db_session, get_profile_loader, require_api_keys
from src.api.upload import save_uploaded_file
from src.worker.profile_loader import ProfileLoader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])
limiter = Limiter(key_func=get_remote_address)

OUTPUT_EXTENSIONS = {".md", ".docx", ".txt", ".json"}


def _normalize_name(value: str) -> str:
    """Lowercase and remove non-alphanumerics for fuzzy filename matching."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _candidate_stems(filename: str) -> set[str]:
    """Generate likely output stem variants from an uploaded job filename."""
    stem = Path(filename).stem
    candidates = {stem}

    # Strip known timestamp prefixes used by upload naming
    patterns = [
        r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}_?",
        r"^\d{8}_\d{6}_?",
        r"^\d{8}_\d{6}-?",
    ]
    for pat in patterns:
        cleaned = re.sub(pat, "", stem)
        if cleaned:
            candidates.add(cleaned)

    # Also normalize common Syncthing conflict token to improve matching
    for c in list(candidates):
        normalized = re.sub(r"sync-conflict-\d{8}-\d{6}-[A-Z0-9]+", "", c, flags=re.IGNORECASE)
        normalized = re.sub(r"__+", "_", normalized).strip("_- ")
        if normalized:
            candidates.add(normalized)

    return {c for c in candidates if c}


def _collect_output_files(job: Job) -> list[dict]:
    """Collect output files for a job using robust stem matching."""
    output_dir = Path("outputs")
    if not output_dir.exists():
        return []

    stems = _candidate_stems(job.filename)
    normalized_stems = {_normalize_name(s) for s in stems if s}
    files: list[dict] = []
    seen_paths: set[str] = set()

    for output_file in output_dir.rglob("*"):
        if not output_file.is_file():
            continue
        if output_file.suffix.lower() not in OUTPUT_EXTENSIONS:
            continue

        out_stem = output_file.stem
        normalized_out_stem = _normalize_name(out_stem)
        if any(s and s in normalized_out_stem for s in normalized_stems):
            out_path = str(output_file)
            if out_path in seen_paths:
                continue
            seen_paths.add(out_path)
            files.append(
                {
                    "type": output_file.suffix.lstrip("."),
                    "path": out_path,
                    "name": output_file.name,
                }
            )

    return files


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_job(
    request: Request,
    file: UploadFile = File(..., description="Audio/video file to transcribe"),
    profile_id: str = Form(..., description="Profile ID for processing"),
    session: Session = Depends(get_db_session),
    profile_loader: ProfileLoader = Depends(get_profile_loader),
    _: None = Depends(require_api_keys),
):
    """
    Create a new transcription job.
    
    Uploads the file, creates a job record, and queues it for processing.
    """
    # Validate profile exists
    profile = profile_loader.get_profile(profile_id)
    if not profile and profile_id not in ["meeting", "supervision", "client", "lecture", "braindump"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid profile_id: {profile_id}"
        )
    
    # Save uploaded file
    file_path = await save_uploaded_file(file, profile_id)
    
    # Get priority from profile config
    job_priority = 5  # Default
    if profile:
        job_priority = getattr(profile, 'priority', 5)
    
    # Create job record
    job = Job(
        profile_id=profile_id,
        filename=str(file_path),
        status="QUEUED",
        priority=job_priority,
    )
    
    session.add(job)
    session.commit()
    session.refresh(job)
    
    return JobResponse.from_orm(job)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    session: Session = Depends(get_db_session),
):
    """Get job details by ID."""
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    # Build response with outputs if complete
    response = JobResponse.from_orm(job)
    
    if job.status == "COMPLETE":
        response.outputs = _collect_output_files(job)
    
    return response


@router.get("/{job_id}/outputs")
async def get_job_outputs(
    job_id: str,
    session: Session = Depends(get_db_session),
):
    """Get list of actual output files for a job with file sizes and sync status."""
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    # Gather stage result output paths
    stage_outputs = session.exec(
        select(StageResult).where(StageResult.job_id == job_id)
    ).all()
    
    files = []
    
    # Check intermediate stage files
    for sr in stage_outputs:
        if sr.output_path:
            p = Path(sr.output_path)
            if p.exists():
                files.append({
                    "path": str(p),
                    "name": p.name,
                    "type": "intermediate",
                    "stage": sr.stage_id,
                    "size_bytes": p.stat().st_size,
                    "exists": True,
                })
    
    # Check final output files with robust matching
    for output in _collect_output_files(job):
        p = Path(output["path"])
        if not p.exists() or not p.is_file():
            continue
        files.append({
            "path": output["path"],
            "name": output["name"],
            "type": output["type"],
            "stage": "final",
            "size_bytes": p.stat().st_size,
            "exists": True,
        })
    
    return {
        "job_id": job_id,
        "profile_id": job.profile_id,
        "files": files,
        "total_files": len(files),
    }


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    profile_id: Optional[str] = Query(None, description="Filter by profile_id"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: Session = Depends(get_db_session),
):
    """List jobs with optional filtering and pagination."""
    # Build query
    statement = select(Job)
    
    if status_filter:
        statement = statement.where(Job.status == status_filter)
    
    if profile_id:
        statement = statement.where(Job.profile_id == profile_id)
    
    # Order by created_at descending
    statement = statement.order_by(Job.created_at.desc())
    
    # Get total count
    count_statement = select(Job)
    if status_filter:
        count_statement = count_statement.where(Job.status == status_filter)
    if profile_id:
        count_statement = count_statement.where(Job.profile_id == profile_id)
    
    total = session.exec(
        select(func.count()).select_from(count_statement.subquery())
    ).one()
    
    # Apply pagination
    statement = statement.limit(limit).offset(offset)
    
    jobs = session.exec(statement).all()
    
    job_responses = []
    for job in jobs:
        resp = JobResponse.from_orm(job)
        # Include stage results for active/recent jobs
        if job.status in ("PROCESSING", "QUEUED") or job.stage_results:
            resp.stage_results = [
                StageResultResponse.from_orm(sr)
                for sr in sorted(job.stage_results, key=lambda s: s.started_at or datetime.min)
            ]
        job_responses.append(resp)
    
    return JobListResponse(
        jobs=job_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    force: bool = Query(False, description="Force delete - removes from DB regardless of status"),
    session: Session = Depends(get_db_session),
):
    """
    Delete a job permanently from the database.
    """
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    # Delete associated stage results first (foreign key constraint)
    stage_results = session.exec(
        select(StageResult).where(StageResult.job_id == job_id)
    ).all()
    for sr in stage_results:
        session.delete(sr)
    
    # Delete the job itself
    session.delete(job)
    session.commit()
    
    return None
