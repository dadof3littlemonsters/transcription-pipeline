# Transcription Pipeline — Recommended Improvements

Apply these changes in order. Each section is a self-contained fix.

---

## CRITICAL FIX: Output Directory Mismatch

There is a bug where output files are written to a non-persistent directory inside the container. They vanish on restart.

**The problem:**
- `docker-compose.yml` mounts `./outputs:/app/outputs` (plural)
- `src/run_worker.py` writes to `Path("output")` → `/app/output` (singular, NOT mounted)
- `src/main.py` lifespan creates `output` directory (singular, NOT mounted)
- `src/config.py` defaults to `/app/outputs` (plural, correct)

The worker's output files are being written to an ephemeral directory that isn't volume-mounted.

### Fix in `src/run_worker.py`

Find:
```python
    output_dir = Path("output").resolve()
```

Replace with:
```python
    output_dir = Path("outputs").resolve()
```

### Fix in `src/main.py` lifespan

Find:
```python
    for directory in ["uploads", "processing", "output", "data", "logs"]:
```

Replace with:
```python
    for directory in ["uploads", "processing", "outputs", "data", "logs"]:
```

### Fix in `src/api/routes/jobs.py` — get_job endpoint

Find:
```python
        output_dir = Path("output")
```

Replace with:
```python
        output_dir = Path("outputs")
```

---

## IMPROVEMENT 1: Per-Stage Pipeline Tracking in the Frontend

The backend already records per-stage progress via the `StageResult` model and publishes updates via Redis → WebSocket. But the frontend doesn't display this. Let's add it.

### 1a. Add stage_results to the job API response

In `src/api/schemas.py`, add a new schema and update `JobResponse`:

Find:
```python
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
    outputs: Optional[List[Dict[str, str]]] = None  # List of {type, path, url}
    
    class Config:
        from_attributes = True
```

Replace with:
```python
class StageResultResponse(BaseModel):
    """Response model for a single stage result."""
    stage_id: str
    status: str  # PENDING, RUNNING, COMPLETE, FAILED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    model_used: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
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
    outputs: Optional[List[Dict[str, str]]] = None
    stage_results: Optional[List[StageResultResponse]] = None
    
    class Config:
        from_attributes = True
```

### 1b. Populate stage_results in the jobs list endpoint

In `src/api/routes/jobs.py`, update the `list_jobs` endpoint to include stage results.

Find (in the `list_jobs` function):
```python
    return JobListResponse(
        jobs=[JobResponse.from_orm(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )
```

Replace with:
```python
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
```

Also add `StageResultResponse` to the imports from schemas at the top of jobs.py:

Find:
```python
from src.api.schemas import JobCreateRequest, JobResponse, JobListResponse
```

Replace with:
```python
from src.api.schemas import JobCreateRequest, JobResponse, JobListResponse, StageResultResponse
```

### 1c. Include stage data in WebSocket broadcasts

In `src/worker/processor.py`, update the `_publish_status` method to include stage info:

Find:
```python
    def _publish_status(self, job: Job):
        """Publish job status update to Redis for WebSocket broadcasting."""
        if not self._redis:
            return
        try:
            self._redis.publish("job_updates", json.dumps({
                "job_id": job.id,
                "status": job.status,
                "current_stage": job.current_stage,
                "error": job.error,
            }))
        except Exception as e:
            logger.warning(f"Failed to publish status update: {e}")
```

Replace with:
```python
    def _publish_status(self, job: Job, stage_detail: dict = None):
        """Publish job status update to Redis for WebSocket broadcasting."""
        if not self._redis:
            return
        try:
            payload = {
                "job_id": job.id,
                "status": job.status,
                "current_stage": job.current_stage,
                "error": job.error,
                "cost_estimate": job.cost_estimate,
            }
            if stage_detail:
                payload["stage_detail"] = stage_detail
            self._redis.publish("job_updates", json.dumps(payload))
        except Exception as e:
            logger.warning(f"Failed to publish status update: {e}")
```

Then update `_record_stage` to pass stage detail:

Find (at the end of `_record_stage`):
```python
        session.add(stage_result)
        job.current_stage = stage_id
        session.add(job)
        session.commit()
        self._publish_status(job)
        return stage_result
```

Replace with:
```python
        session.add(stage_result)
        job.current_stage = stage_id
        session.add(job)
        session.commit()
        self._publish_status(job, stage_detail={
            "stage_id": stage_id,
            "stage_status": status,
            "model_used": kwargs.get("model_used"),
        })
        return stage_result
```

### 1d. Frontend — Add pipeline progress tracker to ControlHub.jsx

Add this new component anywhere before the `ControlHub` default export function. A good place is right after the `StatusBadge` component:

```jsx
// ─── Pipeline Stage Tracker ───
function PipelineTracker({ job, profile }) {
  if (!job.stage_results || job.stage_results.length === 0) {
    // Show basic stage list from profile if no results yet
    if (!profile?.stages || job.status !== "PROCESSING") return null;
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 6 }}>
        {profile.stages.map((stageName, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center" }}>
            <div style={{
              padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 500,
              background: job.current_stage === stageName ? "rgba(96,165,250,0.15)" : "rgba(255,255,255,0.04)",
              color: job.current_stage === stageName ? "#60a5fa" : "rgba(255,255,255,0.25)",
              border: `1px solid ${job.current_stage === stageName ? "rgba(96,165,250,0.3)" : "rgba(255,255,255,0.04)"}`,
            }}>
              {stageName}
            </div>
            {i < profile.stages.length - 1 && (
              <span style={{ color: "rgba(255,255,255,0.1)", fontSize: 10, margin: "0 2px" }}>→</span>
            )}
          </div>
        ))}
      </div>
    );
  }

  const STAGE_STYLES = {
    PENDING: { color: "rgba(255,255,255,0.2)", bg: "rgba(255,255,255,0.03)", border: "rgba(255,255,255,0.04)", icon: "○" },
    RUNNING: { color: "#60a5fa", bg: "rgba(96,165,250,0.12)", border: "rgba(96,165,250,0.3)", icon: "◌" },
    COMPLETE: { color: "#34d399", bg: "rgba(52,211,153,0.1)", border: "rgba(52,211,153,0.2)", icon: "✓" },
    FAILED: { color: "#f87171", bg: "rgba(248,113,113,0.1)", border: "rgba(248,113,113,0.2)", icon: "✗" },
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
      {job.stage_results.map((sr, i) => {
        const style = STAGE_STYLES[sr.status] || STAGE_STYLES.PENDING;
        return (
          <div key={sr.stage_id} style={{ display: "flex", alignItems: "center" }}>
            <div
              title={`${sr.stage_id}: ${sr.status}${sr.model_used ? ` (${sr.model_used})` : ""}${sr.error ? ` — ${sr.error}` : ""}`}
              style={{
                padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 500,
                background: style.bg, color: style.color,
                border: `1px solid ${style.border}`,
                display: "flex", alignItems: "center", gap: 4,
                cursor: "default",
              }}
            >
              <span style={{ fontSize: 9 }}>{style.icon}</span>
              {sr.stage_id}
              {sr.status === "RUNNING" && (
                <span className="spin" style={{ display: "inline-block", fontSize: 9 }}>◑</span>
              )}
            </div>
            {i < job.stage_results.length - 1 && (
              <span style={{ color: "rgba(255,255,255,0.1)", fontSize: 10, margin: "0 2px" }}>→</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

Then update the `JobRow` component to include the tracker. Find the closing `</button>` of the `JobRow` component and add the tracker just before it, inside the grid. 

Actually, a better approach: update the first column of the JobRow grid (the filename/profile area) to include the pipeline tracker below the profile name.

In the `JobRow` component, find:
```jsx
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginTop: 2 }}>
            {profile?.name || job.profile_id}
            {job.current_stage && job.status === "PROCESSING" && (
              <span style={{ color: "rgba(96,165,250,0.8)" }}> · {job.current_stage}</span>
            )}
          </div>
```

Replace with:
```jsx
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginTop: 2 }}>
            {profile?.name || job.profile_id}
            {job.current_stage && job.status === "PROCESSING" && (
              <span style={{ color: "rgba(96,165,250,0.8)" }}> · {job.current_stage}</span>
            )}
          </div>
          {(job.status === "PROCESSING" || job.stage_results?.length > 0) && (
            <PipelineTracker job={job} profile={profile} />
          )}
```

Then update the WebSocket handler in the main `ControlHub` component to handle stage_detail updates. Find:

```jsx
          const { event: evt, data } = JSON.parse(event.data);
          if (evt === "job_update") {
            setJobs(prev => prev.map(j => j.id === data.job_id ? { ...j, ...data } : j));
          }
```

Replace with:
```jsx
          const { event: evt, data } = JSON.parse(event.data);
          if (evt === "job_update") {
            setJobs(prev => prev.map(j => {
              if (j.id !== data.job_id) return j;
              const updated = { ...j, ...data };
              // Merge stage detail into stage_results array
              if (data.stage_detail) {
                const sd = data.stage_detail;
                const existing = (j.stage_results || []).slice();
                const idx = existing.findIndex(sr => sr.stage_id === sd.stage_id);
                const stageEntry = {
                  stage_id: sd.stage_id,
                  status: sd.stage_status,
                  model_used: sd.model_used,
                };
                if (idx >= 0) {
                  existing[idx] = { ...existing[idx], ...stageEntry };
                } else {
                  existing.push(stageEntry);
                }
                updated.stage_results = existing;
              }
              return updated;
            }));
          }
```

---

## IMPROVEMENT 2: Show Output Location in Profile Detail

Users need to know where their files will end up. Update the `ProfileDetail` component in `ControlHub.jsx`.

Find (in `ProfileDetail`, after the syncthing display section):
```jsx
          {profile.syncthing_folder && (
```

Add this block BEFORE that syncthing section:
```jsx
          {/* Output location info */}
          <div style={{
            display: "flex", alignItems: "center", gap: 8, marginTop: 8,
            fontSize: 12, color: "rgba(255,255,255,0.5)",
            background: "rgba(255,255,255,0.03)", padding: "6px 12px", borderRadius: 6,
            width: "fit-content", border: "1px solid rgba(255,255,255,0.05)"
          }}>
            <span style={{ fontWeight: 500 }}>Output:</span>
            <code style={{ fontSize: 11, color: "#a5b4fc" }}>
              outputs/docs/{profile.syncthing_subfolder || profile.id}/
            </code>
          </div>
```

---

## IMPROVEMENT 3: Add Output Folder to Profile Cards

In the `ProfileCard` component, add a subtle output path hint. Find (in ProfileCard):
```jsx
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
            {profile.stage_count} stage{profile.stage_count !== 1 ? "s" : ""} · {jobCount} job{jobCount !== 1 ? "s" : ""}
          </span>
```

Replace with:
```jsx
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
            {profile.stage_count} stage{profile.stage_count !== 1 ? "s" : ""} · {jobCount} job{jobCount !== 1 ? "s" : ""}
            {profile.syncthing_subfolder && (
              <span style={{ color: "rgba(255,255,255,0.15)" }}> · 📁 {profile.syncthing_subfolder}</span>
            )}
          </span>
```

---

## IMPROVEMENT 4: Show Output Path in Create Profile Modal

Users should see where files will go when creating a profile. In the `CreateProfileModal` component, in step 1, after the Syncthing subfolder inputs, add a preview:

Find (at the end of step 1 content, after the syncthing grid):
```jsx
              </div>
            </div>
          ) : (
```

Add before the `) : (` line:
```jsx

              {/* Output path preview */}
              {name && (
                <div style={{
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid rgba(255,255,255,0.04)",
                  borderRadius: 8, padding: "10px 14px",
                }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.3)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
                    Output Location
                  </div>
                  <code style={{ fontSize: 12, color: "#a5b4fc" }}>
                    outputs/docs/{syncthingSubfolder || profileId || autoId(name)}/
                  </code>
                </div>
              )}
```

---

## Verification

After applying all changes:

1. `cd frontend && npm run build`
2. `docker compose build app worker`
3. `docker compose up -d`

Test:
- Create a new profile → verify the output path preview shows correctly
- Upload a file → watch the pipeline stages track in real-time in the job row
- Check that output files appear in `./outputs/docs/` on the host (not `./output/`)
- Delete a job → verify it stays deleted after refresh
- Open the log console → verify stage transitions appear in the logs
