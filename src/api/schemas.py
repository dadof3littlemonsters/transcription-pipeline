"""
Pydantic schemas for API request/response models.
"""

from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


# Job Schemas
class JobCreateRequest(BaseModel):
    """Request model for creating a new job."""
    profile_id: str = Field(..., description="Profile ID to use for processing")
    # Note: file is handled separately via UploadFile in the endpoint

class StageResultResponse(BaseModel):
    """Response model for a single stage result."""
    stage_id: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    model_used: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_estimate: float = 0.0
    error: Optional[str] = None

    class Config:
        from_attributes = True


class JobResponse(BaseModel):
    """Response model for job details."""
    id: str
    profile_id: str
    filename: str
    status: str
    current_stage: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    cost_estimate: float
    priority: int = 5
    outputs: Optional[List[Dict[str, str]]] = None
    stage_results: Optional[List[StageResultResponse]] = None
    
    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    """Response model for paginated job list."""
    jobs: List[JobResponse]
    total: int
    limit: int
    offset: int


# Profile Schemas
class ProfileStageInfo(BaseModel):
    """Information about a single processing stage."""
    name: str
    model: str
    provider: Optional[str] = None
    description: Optional[str] = None


class ProfileCreateStage(BaseModel):
    """Request model for creating a profile stage."""
    name: str
    model: str = "deepseek-chat"
    provider: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 4096
    prompt_content: str = ""
    prompt_file: Optional[str] = None  # Auto-generated if not provided
    requires_previous: bool = False
    save_intermediate: bool = True
    filename_suffix: str = ""


class NotificationConfigRequest(BaseModel):
    """Notification settings for a profile."""
    ntfy_topic: Optional[str] = None
    ntfy_url: Optional[str] = None
    discord_webhook: Optional[str] = None
    pushover_user: Optional[str] = None
    pushover_token: Optional[str] = None


class ProfileCreateRequest(BaseModel):
    """Request model for creating a new profile."""
    id: str
    name: str
    description: Optional[str] = None
    skip_diarization: bool = False
    icon: Optional[str] = None
    priority: int = 5
    syncthing_folder: Optional[str] = None
    syncthing_subfolder: Optional[str] = None
    notifications: Optional[NotificationConfigRequest] = None
    stages: List[ProfileCreateStage]


class ProfileResponse(BaseModel):
    """Response model for profile metadata."""
    id: str
    name: str
    description: Optional[str] = None
    stage_count: int
    stages: Optional[List[str]] = None
    syncthing_folder: Optional[str] = None
    syncthing_subfolder: Optional[str] = None
    priority: int = 5
    has_notifications: bool = False


class ProfileDetailResponse(BaseModel):
    """Response model for full profile details."""
    id: str
    name: str
    description: Optional[str] = None
    stages: List[ProfileStageInfo]
    
    
# Health Check Schemas
class HealthCheckResponse(BaseModel):
    """Response model for health check."""
    status: str
    service: str
    checks: Dict[str, bool]
    timestamp: datetime


class ReadinessCheckResponse(BaseModel):
    """Response model for readiness check."""
    ready: bool
    checks: Dict[str, bool]
    missing_keys: Optional[List[str]] = None
