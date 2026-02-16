"""
Cost tracking API routes.
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from src.api.models import Job, StageResult


router = APIRouter(prefix="/api/costs", tags=["Costs"])


def get_db_session():
    """Get a database session."""
    from sqlmodel import create_engine
    DB_URL = "sqlite:///data/jobs.db"
    engine = create_engine(DB_URL)
    with Session(engine) as session:
        yield session


@router.get("/summary")
async def cost_summary(session: Session = Depends(get_db_session)):
    """Get cost summary across all jobs with per-stage breakdown."""
    jobs = session.exec(select(Job)).all()
    
    total_cost = sum(j.cost_estimate or 0 for j in jobs)
    by_profile = {}
    for j in jobs:
        pid = j.profile_id or "unknown"
        by_profile.setdefault(pid, 0)
        by_profile[pid] += j.cost_estimate or 0
    
    completed_jobs = [j for j in jobs if j.status == "COMPLETE"]
    avg_cost = total_cost / len(completed_jobs) if completed_jobs else 0
    
    # Per-stage cost breakdown
    stage_results = session.exec(select(StageResult)).all()
    by_stage = {}
    by_model = {}
    for sr in stage_results:
        if sr.cost_estimate:
            by_stage.setdefault(sr.stage_id, {"cost": 0, "count": 0, "tokens": 0})
            by_stage[sr.stage_id]["cost"] += sr.cost_estimate
            by_stage[sr.stage_id]["count"] += 1
            by_stage[sr.stage_id]["tokens"] += (sr.input_tokens or 0) + (sr.output_tokens or 0)
            
            model = sr.model_used or "unknown"
            by_model.setdefault(model, {"cost": 0, "count": 0})
            by_model[model]["cost"] += sr.cost_estimate
            by_model[model]["count"] += 1
    
    # Recent costs (last 20 completed jobs)
    recent = sorted(completed_jobs, key=lambda j: j.completed_at or j.created_at, reverse=True)[:20]
    recent_costs = [
        {
            "job_id": j.id,
            "profile_id": j.profile_id,
            "cost": j.cost_estimate or 0,
            "completed_at": (j.completed_at or j.created_at).isoformat() if (j.completed_at or j.created_at) else None,
        }
        for j in recent
    ]
    
    return {
        "total_cost": round(total_cost, 6),
        "by_profile": {k: round(v, 6) for k, v in by_profile.items()},
        "by_stage": {k: {**v, "cost": round(v["cost"], 6)} for k, v in by_stage.items()},
        "by_model": {k: {**v, "cost": round(v["cost"], 6)} for k, v in by_model.items()},
        "job_count": len(jobs),
        "completed_count": len(completed_jobs),
        "avg_cost": round(avg_cost, 6),
        "recent": recent_costs,
    }
