"""
Job management API routes.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, Request, status, Query
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlmodel import Session, select

from src.api.models import Job, StageResult
from src.api.schemas import JobCreateRequest, JobResponse, JobListResponse
from src.api.dependencies import get_db_session, get_profile_loader, require_api_keys
from src.api.upload import save_uploaded_file
from src.worker.profile_loader import ProfileLoader

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])
limiter = Limiter(key_func=get_remote_address)


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
    
    # Create job record
    job = Job(
        profile_id=profile_id,
        filename=str(file_path),
        status="QUEUED",
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
        # Look for output files
        output_dir = Path("output")
        job_stem = Path(job.filename).stem
        
        outputs = []
        for output_file in output_dir.rglob(f"{job_stem}*"):
            if output_file.is_file():
                outputs.append({
                    "type": output_file.suffix[1:],  # Remove leading dot
                    "path": str(output_file),
                    "name": output_file.name,
                })
        
        response.outputs = outputs
    
    return response


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
    
    total = len(session.exec(count_statement).all())
    
    # Apply pagination
    statement = statement.limit(limit).offset(offset)
    
    jobs = session.exec(statement).all()
    
    return JobListResponse(
        jobs=[JobResponse.from_orm(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    session: Session = Depends(get_db_session),
):
    """
    Cancel or delete a job.
    
    If the job is QUEUED or PROCESSING, it will be marked as CANCELLED.
    """
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    # Only allow cancellation of queued/processing jobs
    if job.status in ["QUEUED", "PROCESSING"]:
        job.status = "CANCELLED"
        job.error = "Cancelled by user"
        session.add(job)
        session.commit()
    elif job.status in ["COMPLETE", "FAILED"]:
        # For completed/failed jobs, just delete the record
        session.delete(job)
        session.commit()
    
    return None
