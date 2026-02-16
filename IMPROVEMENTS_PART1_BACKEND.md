# Pipeline Improvements — Part 1: Backend

Apply all changes in order.

---

## IMPROVEMENT 1: Per-Stage Recording in Processor

Currently the processor records one "formatting" stage for the entire multi-stage pipeline. We need to record each individual stage so we get per-stage costs, timing, and resume capability.

### 1a. Add `priority` and `notification_config` fields to the Job model

In `src/api/models.py`:

Find:
```python
    cost_estimate: float = 0.0
    
    # Relationship
    stage_results: List["StageResult"] = Relationship(back_populates="job")
```

Replace with:
```python
    cost_estimate: float = 0.0
    priority: int = Field(default=5, index=True)  # 1=highest, 10=lowest
    
    # Relationship
    stage_results: List["StageResult"] = Relationship(back_populates="job")
```

Also add a `cost_estimate` field to `StageResult` so we can track per-stage costs:

Find:
```python
    model_used: Optional[str] = None
    output_path: Optional[str] = None
    error: Optional[str] = None
```

Replace with:
```python
    model_used: Optional[str] = None
    cost_estimate: float = 0.0
    output_path: Optional[str] = None
    error: Optional[str] = None
```

**IMPORTANT:** After this change you need to add the column to existing databases. Create a migration script `scripts/migrate_add_fields.py`:

```python
"""One-time migration to add new fields to existing database."""
import sqlite3
import sys

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/jobs.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Add priority column to job table
try:
    cursor.execute("ALTER TABLE job ADD COLUMN priority INTEGER DEFAULT 5")
    print("Added 'priority' column to job table")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e).lower():
        print("'priority' column already exists")
    else:
        raise

# Add cost_estimate column to stageresult table
try:
    cursor.execute("ALTER TABLE stageresult ADD COLUMN cost_estimate REAL DEFAULT 0.0")
    print("Added 'cost_estimate' column to stageresult table")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e).lower():
        print("'cost_estimate' column already exists")
    else:
        raise

conn.commit()
conn.close()
print("Migration complete")
```

Run this before deploying: `python scripts/migrate_add_fields.py data/jobs.db`

### 1b. Rewrite `_process_with_profile` to record individual stages with resume

In `src/worker/processor.py`, replace the entire `_process_with_profile` method:

Find:
```python
    def _process_with_profile(
        self,
        session: Session,
        job: Job,
        audio_path: Path,
        transcript_data: Dict,
        profile_id: str,
        result: Dict
    ):
        """Process using multi-stage formatter."""
```

Replace the entire method (from `def _process_with_profile` through to the `self._send_email(` call and the line after it) with:

```python
    def _process_with_profile(
        self,
        session: Session,
        job: Job,
        audio_path: Path,
        transcript_data: Dict,
        profile_id: str,
        result: Dict
    ):
        """Process using multi-stage formatter with per-stage tracking and resume."""
        logger.info(f"Processing with profile: {profile_id}")
        
        whisper_segments = transcript_data["segments"]
        full_text = transcript_data["text"]
        duration = transcript_data["duration"]
        
        # Build raw transcript
        raw_transcript = self._build_raw_transcript(whisper_segments)
        
        # Get the profile and its stages
        profile = self.profile_loader.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile not found: {profile_id}")
        
        from .providers import resolve_provider
        from .pricing import estimate_cost
        
        current_input = raw_transcript
        previous_outputs = {}
        stage_results_data = {}
        total_cost = 0.0
        
        # Process each stage individually with resume support
        for i, stage in enumerate(profile.stages):
            stage_id = stage.name
            
            # Check if this stage was already completed (resume support)
            cached = self._get_stage_result(session, job.id, stage_id)
            if cached and cached.output_path:
                cached_path = Path(cached.output_path)
                if cached_path.exists():
                    logger.info(f"Resuming: Stage '{stage_id}' already complete, loading cached output")
                    try:
                        current_input = cached_path.read_text(encoding="utf-8")
                        previous_outputs[stage_id] = current_input
                        stage_results_data[stage_id] = current_input
                        total_cost += cached.cost_estimate or 0.0
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to load cached stage output: {e}. Re-running stage.")
            
            # Record stage as RUNNING
            self._record_stage(session, job, stage_id, "RUNNING", model_used=stage.model)
            
            try:
                # Resolve provider
                provider_config = resolve_provider(stage.model, stage.provider or None)
                
                # Build prompt
                prompt_kwargs = {"transcript": current_input}
                if "{cleaned_transcript}" in stage.prompt_template and "clean" in previous_outputs:
                    prompt_kwargs["cleaned_transcript"] = previous_outputs.get("clean", current_input)
                elif "{cleaned_transcript}" in stage.prompt_template:
                    prompt_kwargs["cleaned_transcript"] = current_input
                
                prompt = stage.prompt_template.format(**prompt_kwargs)
                
                # Call LLM using the formatter's _call_api
                multi_formatter = self._get_multi_stage_formatter(profile_id)
                output, usage_info = multi_formatter._call_api(
                    prompt=prompt,
                    system_message=stage.system_message,
                    model=stage.model,
                    temperature=stage.temperature,
                    max_tokens=stage.max_tokens,
                    timeout=stage.timeout,
                    provider_config=provider_config,
                )
                
                # Calculate per-stage cost
                input_tokens = usage_info.get("input_tokens", 0)
                output_tokens = usage_info.get("output_tokens", 0)
                stage_cost = estimate_cost(stage.model, input_tokens, output_tokens)
                total_cost += stage_cost
                
                # Save intermediate output for resume
                job_data_dir = self.processing_dir / "job_data" / job.id
                job_data_dir.mkdir(parents=True, exist_ok=True)
                stage_output_path = job_data_dir / f"stage_{stage_id}.txt"
                stage_output_path.write_text(output, encoding="utf-8")
                
                # Record stage as COMPLETE with full metrics
                self._record_stage(
                    session, job, stage_id, "COMPLETE",
                    model_used=stage.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_estimate=stage_cost,
                    output_path=str(stage_output_path),
                )
                
                # Update for next stage
                current_input = output
                previous_outputs[stage_id] = output
                stage_results_data[stage_id] = output
                
                logger.info(f"  Stage '{stage_id}' complete ({len(output)} chars, ${stage_cost:.6f})")
                
            except Exception as e:
                logger.error(f"  Stage '{stage_id}' failed: {e}")
                self._record_stage(session, job, stage_id, "FAILED", error=str(e), model_used=stage.model)
                raise  # Fail the job — on next run it will resume from this stage
        
        # Update total cost
        job.cost_estimate = total_cost
        session.add(job)
        session.commit()
        
        # Output Generation
        self._record_stage(session, job, "output", "RUNNING")
        
        # Build stage outputs for file generation
        stage_outputs = []
        for stage in profile.stages:
            if stage.name in stage_results_data and stage.save_intermediate:
                stage_outputs.append({
                    "stage": stage.name,
                    "suffix": stage.filename_suffix,
                    "content": stage_results_data[stage.name],
                })
        
        metadata = {
            "duration": duration,
            "processed_at": datetime.now().isoformat(),
            "profile": profile_id,
        }
        
        syncthing = getattr(profile, 'syncthing', None)
        user_subdir = syncthing.subfolder if syncthing else None
        docs_dir = self.output_generator.get_user_docs_dir(user_subdir)
        
        all_outputs = []
        for stage_output in stage_outputs:
            outputs = self.output_generator.generate_multi_stage_output(
                content=stage_output["content"],
                filename_base=audio_path.stem,
                suffix=stage_output["suffix"],
                stage_name=stage_output["stage"],
                metadata=metadata,
                docs_dir=docs_dir
            )
            all_outputs.extend(outputs)
            
        result["outputs"] = {"stage_files": all_outputs}
        result["success"] = True
        
        self._record_stage(session, job, "output", "COMPLETE")
        
        # Notifications
        self._send_notifications(profile_id, profile, audio_path.stem, all_outputs, total_cost)
```

### 1c. Add notification dispatcher

Add this method to the `JobProcessor` class, after `_send_email`:

```python
    def _send_notifications(self, profile_id: str, profile, lecture_name: str, outputs: list, total_cost: float = 0.0):
        """Send all configured notifications for a completed job."""
        # Email (existing)
        self._send_email(profile_id, lecture_name, outputs)
        
        # Webhook notifications (Ntfy, Discord, Pushover)
        notification_config = getattr(profile, 'notifications', None)
        if not notification_config:
            return
        
        output_names = [Path(o.get("path", "")).name for o in outputs if o.get("type") == "docx"]
        summary = f"Pipeline complete: {lecture_name} ({len(output_names)} files, ${total_cost:.4f})"
        
        # Ntfy
        ntfy_topic = getattr(notification_config, 'ntfy_topic', None)
        ntfy_url = getattr(notification_config, 'ntfy_url', None) or os.getenv("NTFY_URL", "https://ntfy.sh")
        if ntfy_topic:
            try:
                import requests as req
                req.post(
                    f"{ntfy_url}/{ntfy_topic}",
                    data=summary,
                    headers={
                        "Title": f"Transcription: {lecture_name}",
                        "Priority": "default",
                        "Tags": "white_check_mark",
                    },
                    timeout=10,
                )
                logger.info(f"Ntfy notification sent to topic: {ntfy_topic}")
            except Exception as e:
                logger.warning(f"Ntfy notification failed: {e}")
        
        # Discord
        discord_webhook = getattr(notification_config, 'discord_webhook', None) or os.getenv("DISCORD_WEBHOOK_URL")
        if discord_webhook:
            try:
                import requests as req
                req.post(
                    discord_webhook,
                    json={
                        "content": summary,
                        "embeds": [{
                            "title": f"Transcription Complete",
                            "description": f"**{lecture_name}**\nProfile: {profile_id}\nCost: ${total_cost:.4f}\nFiles: {', '.join(output_names)}",
                            "color": 3066993,  # Green
                        }]
                    },
                    timeout=10,
                )
                logger.info("Discord notification sent")
            except Exception as e:
                logger.warning(f"Discord notification failed: {e}")
        
        # Pushover
        pushover_user = getattr(notification_config, 'pushover_user', None) or os.getenv("PUSHOVER_USER_KEY")
        pushover_token = getattr(notification_config, 'pushover_token', None) or os.getenv("PUSHOVER_APP_TOKEN")
        if pushover_user and pushover_token:
            try:
                import requests as req
                req.post(
                    "https://api.pushover.net/1/messages.json",
                    data={
                        "token": pushover_token,
                        "user": pushover_user,
                        "title": f"Transcription: {lecture_name}",
                        "message": summary,
                    },
                    timeout=10,
                )
                logger.info("Pushover notification sent")
            except Exception as e:
                logger.warning(f"Pushover notification failed: {e}")
```

---

## IMPROVEMENT 2: Add NotificationConfig to types

In `src/worker/types.py`, add a new dataclass and update DegreeProfile:

Find:
```python
@dataclass
class DegreeProfile:
    """Defines a degree-specific processing profile."""
    name: str
    stages: List[ProcessingStage]
    skip_diarization: bool = False
    description: str = ""
    syncthing: Optional[SyncthingConfig] = None
```

Replace with:
```python
@dataclass
class NotificationConfig:
    """Notification configuration for a profile."""
    ntfy_topic: str = ""
    ntfy_url: str = ""  # Defaults to https://ntfy.sh
    discord_webhook: str = ""
    pushover_user: str = ""
    pushover_token: str = ""


@dataclass
class DegreeProfile:
    """Defines a degree-specific processing profile."""
    name: str
    stages: List[ProcessingStage]
    skip_diarization: bool = False
    description: str = ""
    syncthing: Optional[SyncthingConfig] = None
    notifications: Optional[NotificationConfig] = None
    priority: int = 5  # Default priority 1=highest, 10=lowest
```

### 2b. Parse notifications in ProfileLoader

In `src/worker/profile_loader.py`, in `_parse_profile`, add notification config parsing.

Find (after the syncthing parsing block):
```python
        profile = DegreeProfile(
            name=profile_name,
            stages=stages,
            skip_diarization=data.get("skip_diarization", False),
            description=data.get("description", ""),
            syncthing=syncthing,
        )
```

Replace with:
```python
        # Parse notification config
        notif_data = data.get("notifications")
        notifications = None
        if notif_data and isinstance(notif_data, dict):
            notifications = NotificationConfig(
                ntfy_topic=notif_data.get("ntfy_topic", ""),
                ntfy_url=notif_data.get("ntfy_url", ""),
                discord_webhook=notif_data.get("discord_webhook", ""),
                pushover_user=notif_data.get("pushover_user", ""),
                pushover_token=notif_data.get("pushover_token", ""),
            )
        
        profile = DegreeProfile(
            name=profile_name,
            stages=stages,
            skip_diarization=data.get("skip_diarization", False),
            description=data.get("description", ""),
            syncthing=syncthing,
            notifications=notifications,
            priority=data.get("priority", 5),
        )
```

Also add `NotificationConfig` to the import at the top of profile_loader.py:

Find:
```python
from .types import DegreeProfile, ProcessingStage, SyncthingConfig
```

Replace with:
```python
from .types import DegreeProfile, ProcessingStage, SyncthingConfig, NotificationConfig
```

---

## IMPROVEMENT 3: Priority Queue

### 3a. Update the worker's job pickup to respect priority

In `src/run_worker.py`:

Find:
```python
def get_next_job():
    """Get the next QUEUED job from the database."""
    with Session(engine) as session:
        statement = select(Job).where(Job.status == "QUEUED").order_by(Job.created_at).limit(1)
        return session.exec(statement).first()
```

Replace with:
```python
def get_next_job():
    """Get the next QUEUED job from the database, respecting priority."""
    with Session(engine) as session:
        statement = (
            select(Job)
            .where(Job.status == "QUEUED")
            .order_by(Job.priority.asc(), Job.created_at.asc())
            .limit(1)
        )
        return session.exec(statement).first()
```

### 3b. Set job priority from profile on job creation

In `src/api/routes/jobs.py`, in the `create_job` endpoint:

Find:
```python
    # Create job record
    job = Job(
        profile_id=profile_id,
        filename=str(file_path),
        status="QUEUED",
    )
```

Replace with:
```python
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
```

### 3c. Add priority to profile create request schema

In `src/api/schemas.py`, add `priority` to `ProfileCreateRequest`:

Find:
```python
class ProfileCreateRequest(BaseModel):
    """Request model for creating a new profile."""
    id: str
    name: str
    description: Optional[str] = None
    skip_diarization: bool = False
    icon: Optional[str] = None
    syncthing_folder: Optional[str] = None
    syncthing_subfolder: Optional[str] = None
    stages: List[ProfileCreateStage]
```

Replace with:
```python
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
```

### 3d. Write notification and priority config to YAML on profile creation

In `src/api/routes/profiles.py`, in the `create_profile` function, where the YAML data is built:

Find:
```python
    # Add syncthing config if provided
    if request.syncthing_folder:
        yaml_data["syncthing"] = {
            "share_folder": request.syncthing_folder,
            "subfolder": request.syncthing_subfolder or "",
        }
```

Replace with:
```python
    # Priority
    yaml_data["priority"] = request.priority
    
    # Add syncthing config if provided
    if request.syncthing_folder:
        yaml_data["syncthing"] = {
            "share_folder": request.syncthing_folder,
            "subfolder": request.syncthing_subfolder or "",
        }
    
    # Add notification config if provided
    if request.notifications:
        notif = request.notifications
        notif_data = {}
        if notif.ntfy_topic: notif_data["ntfy_topic"] = notif.ntfy_topic
        if notif.ntfy_url: notif_data["ntfy_url"] = notif.ntfy_url
        if notif.discord_webhook: notif_data["discord_webhook"] = notif.discord_webhook
        if notif.pushover_user: notif_data["pushover_user"] = notif.pushover_user
        if notif.pushover_token: notif_data["pushover_token"] = notif.pushover_token
        if notif_data:
            yaml_data["notifications"] = notif_data
```

---

## IMPROVEMENT 4: Prompt Dry-Run Endpoint

Add a new endpoint that runs a single stage against a sample transcript without creating a job.

In `src/api/routes/profiles.py`, add this endpoint:

```python
@router.post("/{profile_id}/dry-run")
async def dry_run_stage(
    profile_id: str,
    body: dict,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """
    Run a single stage against sample text without creating a job.
    
    Body: {
        "stage_index": 0,
        "transcript": "sample text...",
        "job_id": null  // Optional: pull transcript from a previous job's transcription
    }
    """
    profile = profile_loader.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    stage_index = body.get("stage_index", 0)
    if stage_index < 0 or stage_index >= len(profile.stages):
        raise HTTPException(status_code=400, detail=f"Invalid stage_index. Profile has {len(profile.stages)} stages.")
    
    # Get transcript: from body or from a previous job
    transcript = body.get("transcript")
    job_id = body.get("job_id")
    
    if not transcript and job_id:
        # Try to load from job's transcription cache
        from pathlib import Path
        transcription_path = Path("processing/job_data") / job_id / "transcription.json"
        if transcription_path.exists():
            import json
            with open(transcription_path) as f:
                data = json.load(f)
                transcript = data.get("text", "")
        
        if not transcript:
            raise HTTPException(status_code=400, detail=f"Could not load transcript from job {job_id}")
    
    if not transcript:
        raise HTTPException(status_code=400, detail="Provide 'transcript' or 'job_id'")
    
    # Truncate for safety (dry runs shouldn't be full-length)
    max_chars = body.get("max_chars", 5000)
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n\n[... truncated for dry-run ...]"
    
    stage = profile.stages[stage_index]
    
    try:
        from src.worker.providers import resolve_provider
        from src.worker.formatter import MultiStageFormatter
        from src.worker.pricing import estimate_cost
        import os
        
        provider_config = resolve_provider(stage.model, stage.provider or None)
        
        # Build prompt
        prompt_kwargs = {"transcript": transcript}
        if "{cleaned_transcript}" in stage.prompt_template:
            prompt_kwargs["cleaned_transcript"] = transcript
        
        prompt = stage.prompt_template.format(**prompt_kwargs)
        
        # Create a temporary formatter to call the API
        default_key = (
            os.getenv("DEEPSEEK_API_KEY") or
            os.getenv("OPENROUTER_API_KEY") or
            os.getenv("OPENAI_API_KEY") or
            ""
        )
        
        formatter = MultiStageFormatter(
            api_key=default_key,
            prompts_dir=profile_loader.prompts_dir,
            profile=profile,
        )
        
        output, usage_info = formatter._call_api(
            prompt=prompt,
            system_message=stage.system_message,
            model=stage.model,
            temperature=stage.temperature,
            max_tokens=stage.max_tokens,
            timeout=stage.timeout,
            provider_config=provider_config,
        )
        
        input_tokens = usage_info.get("input_tokens", 0)
        output_tokens = usage_info.get("output_tokens", 0)
        cost = estimate_cost(stage.model, input_tokens, output_tokens)
        
        return {
            "stage": stage.name,
            "model": stage.model,
            "provider": provider_config.name,
            "output": output,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": round(cost, 6),
            "input_length": len(transcript),
            "output_length": len(output),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dry-run failed: {str(e)}")
```

---

## IMPROVEMENT 5: Output File Browser Endpoint

Add an endpoint to list actual output files for a job.

In `src/api/routes/jobs.py`, add this endpoint after the existing `get_job` endpoint:

```python
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
    
    # Check final output files
    output_dir = Path("outputs")
    job_stem = Path(job.filename).stem
    
    # Remove timestamp prefix for matching
    import re
    clean_stem = re.sub(r'^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}_?', '', job_stem)
    
    for output_file in output_dir.rglob(f"*{clean_stem}*"):
        if output_file.is_file():
            files.append({
                "path": str(output_file),
                "name": output_file.name,
                "type": output_file.suffix.lstrip("."),
                "stage": "final",
                "size_bytes": output_file.stat().st_size,
                "exists": True,
            })
    
    return {
        "job_id": job_id,
        "profile_id": job.profile_id,
        "files": files,
        "total_files": len(files),
    }
```

---

## IMPROVEMENT 6: Per-stage cost breakdown in cost summary

In `src/api/routes/costs.py`, enhance the summary with per-stage breakdowns:

Find the entire `cost_summary` function and replace with:

```python
@router.get("/summary")
async def cost_summary(session: Session = Depends(get_db_session)):
    """Get cost summary across all jobs with per-stage breakdown."""
    from src.api.models import StageResult
    
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
```

Also add the `StageResult` import at the top of costs.py if not present:

Find:
```python
from src.api.models import Job
```

Replace with:
```python
from src.api.models import Job, StageResult
```

---

## Verification

After applying all backend changes:

1. Run migration: `python scripts/migrate_add_fields.py data/jobs.db`
2. Rebuild: `docker compose build app worker`
3. Restart: `docker compose up -d`
4. Test dry-run: `curl -X POST http://localhost:8888/api/profiles/social_work_lecture/dry-run -H "Content-Type: application/json" -d '{"stage_index": 0, "transcript": "This is a test lecture about social work..."}'`
5. Check cost summary: `curl http://localhost:8888/api/costs/summary` — should now include `by_stage` and `by_model`
6. Submit a job and verify individual stages appear in the stage_results
