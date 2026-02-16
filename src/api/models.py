import uuid
from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship

from sqlmodel import SQLModel, Field, Relationship

class Job(SQLModel, table=True):
    __tablename__ = "job"
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    profile_id: str = Field(index=True)
    filename: str
    status: str = Field(default="QUEUED", index=True)  # QUEUED, PROCESSING, COMPLETE, FAILED, CANCELLED
    current_stage: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    cost_estimate: float = 0.0
    priority: int = Field(default=5, index=True)  # 1=highest, 10=lowest
    
    # Relationship
    stage_results: List["StageResult"] = Relationship(back_populates="job")

class StageResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(foreign_key="job.id")
    stage_id: str  # e.g., "clean", "analyse"
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETE, FAILED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    input_tokens: int = 0
    output_tokens: int = 0
    model_used: Optional[str] = None
    cost_estimate: float = 0.0
    output_path: Optional[str] = None
    error: Optional[str] = None
    
    # Relationship
    job: Job = Relationship(back_populates="stage_results")
