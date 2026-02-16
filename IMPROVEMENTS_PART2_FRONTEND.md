# Pipeline Improvements — Part 2: Frontend

Apply after Part 1 backend changes are complete.

---

## CHANGE 1: Add StageResultResponse to schemas and API responses

In `src/api/schemas.py`, add the stage result response model. 

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
```

Also add `priority` and `notifications` to `ProfileResponse`:

Find:
```python
class ProfileResponse(BaseModel):
    """Response model for profile metadata."""
    id: str
    name: str
    description: Optional[str] = None
    stage_count: int
    stages: Optional[List[str]] = None  # Stage names
    syncthing_folder: Optional[str] = None
    syncthing_subfolder: Optional[str] = None
```

Replace with:
```python
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
```

### 1b. Populate stage_results and priority in job list endpoint

In `src/api/routes/jobs.py`, update the `list_jobs` endpoint:

Add import at top:
```python
from src.api.schemas import JobCreateRequest, JobResponse, JobListResponse, StageResultResponse
```

Find (in `list_jobs`):
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
        if job.stage_results:
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

### 1c. Update list_profiles to include priority and notification status

In `src/api/routes/profiles.py`, in the `list_profiles` function:

Find:
```python
            profiles.append(ProfileResponse(
                id=profile_id,
                name=profile.name,
                description=getattr(profile, 'description', ''),
                stage_count=len(profile.stages),
                stages=[stage.name for stage in profile.stages],
                syncthing_folder=profile.syncthing.share_folder if profile.syncthing else None,
                syncthing_subfolder=profile.syncthing.subfolder if profile.syncthing else None,
            ))
```

Replace with:
```python
            has_notif = bool(getattr(profile, 'notifications', None) and (
                profile.notifications.ntfy_topic or
                profile.notifications.discord_webhook or
                profile.notifications.pushover_user
            ))
            profiles.append(ProfileResponse(
                id=profile_id,
                name=profile.name,
                description=getattr(profile, 'description', ''),
                stage_count=len(profile.stages),
                stages=[stage.name for stage in profile.stages],
                syncthing_folder=profile.syncthing.share_folder if profile.syncthing else None,
                syncthing_subfolder=profile.syncthing.subfolder if profile.syncthing else None,
                priority=getattr(profile, 'priority', 5),
                has_notifications=has_notif,
            ))
```

---

## CHANGE 2: Pipeline Stage Tracker Component

In `frontend/src/ControlHub.jsx`, add this component before the main `ControlHub` export function. Place it near the existing `StatusBadge` helper component:

```jsx
function PipelineTracker({ job }) {
  const stageResults = job.stage_results || [];
  if (stageResults.length === 0 && job.status !== "PROCESSING") return null;

  const STAGE_STYLES = {
    PENDING:  { color: "rgba(255,255,255,0.2)", bg: "rgba(255,255,255,0.03)", border: "rgba(255,255,255,0.04)", icon: "○" },
    RUNNING:  { color: "#60a5fa", bg: "rgba(96,165,250,0.12)", border: "rgba(96,165,250,0.3)", icon: "◌" },
    COMPLETE: { color: "#34d399", bg: "rgba(52,211,153,0.1)", border: "rgba(52,211,153,0.2)", icon: "✓" },
    FAILED:   { color: "#f87171", bg: "rgba(248,113,113,0.1)", border: "rgba(248,113,113,0.2)", icon: "✗" },
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
      {stageResults.map((sr, i) => {
        const s = STAGE_STYLES[sr.status] || STAGE_STYLES.PENDING;
        const costStr = sr.cost_estimate > 0 ? ` · $${sr.cost_estimate.toFixed(4)}` : "";
        const tokenStr = (sr.input_tokens || sr.output_tokens)
          ? ` · ${((sr.input_tokens + sr.output_tokens) / 1000).toFixed(1)}k tok`
          : "";
        return (
          <div key={sr.stage_id} style={{ display: "flex", alignItems: "center" }}>
            <div
              title={`${sr.stage_id}: ${sr.status}${sr.model_used ? ` (${sr.model_used})` : ""}${costStr}${tokenStr}${sr.error ? ` — ${sr.error}` : ""}`}
              style={{
                padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 500,
                background: s.bg, color: s.color, border: `1px solid ${s.border}`,
                display: "flex", alignItems: "center", gap: 4, cursor: "default",
              }}
            >
              <span style={{ fontSize: 9 }}>{s.icon}</span>
              {sr.stage_id}
            </div>
            {i < stageResults.length - 1 && (
              <span style={{ color: "rgba(255,255,255,0.1)", fontSize: 10, margin: "0 2px" }}>→</span>
            )}
          </div>
        );
      })}
      {job.cost_estimate > 0 && (
        <span style={{ fontSize: 10, color: "rgba(255,255,255,0.2)", marginLeft: 4 }}>
          ${job.cost_estimate.toFixed(4)}
        </span>
      )}
    </div>
  );
}
```

### 2b. Add PipelineTracker to job rows

In the `JobRow` component, find the profile name display:

```jsx
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginTop: 2 }}>
            {profile?.name || job.profile_id}
            {job.current_stage && job.status === "PROCESSING" && (
              <span style={{ color: "rgba(96,165,250,0.8)" }}> · {job.current_stage}</span>
            )}
          </div>
```

Add immediately after:
```jsx
          <PipelineTracker job={job} />
```

### 2c. Update WebSocket handler for per-stage updates

Find the WebSocket message handler in ControlHub:

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
              const updated = { ...j, status: data.status, current_stage: data.current_stage, error: data.error, cost_estimate: data.cost_estimate || j.cost_estimate };
              if (data.stage_detail) {
                const sd = data.stage_detail;
                const existing = (j.stage_results || []).slice();
                const idx = existing.findIndex(sr => sr.stage_id === sd.stage_id);
                const entry = { stage_id: sd.stage_id, status: sd.stage_status, model_used: sd.model_used };
                if (idx >= 0) existing[idx] = { ...existing[idx], ...entry };
                else existing.push(entry);
                updated.stage_results = existing;
              }
              return updated;
            }));
          }
```

---

## CHANGE 3: Add Notifications and Priority to Create Profile Modal

In the `CreateProfileModal` component, add notification config state after the existing Syncthing state:

```javascript
  const [priority, setPriority] = useState(5);
  const [ntfyTopic, setNtfyTopic] = useState("");
  const [discordWebhook, setDiscordWebhook] = useState("");
  const [pushoverUser, setPushoverUser] = useState("");
  const [pushoverToken, setPushoverToken] = useState("");
```

### 3b. Add UI fields in step 1

After the Syncthing section (and before the output path preview), add:

```jsx
              {/* Priority */}
              <div>
                <label style={labelStyle}>Queue Priority</label>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <input
                    type="range" min="1" max="10" value={priority}
                    onChange={e => setPriority(parseInt(e.target.value))}
                    style={{ flex: 1, accentColor: "#60a5fa" }}
                  />
                  <span style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", minWidth: 60 }}>
                    {priority <= 3 ? "High" : priority <= 7 ? "Normal" : "Low"} ({priority})
                  </span>
                </div>
              </div>

              {/* Notifications */}
              <div>
                <label style={labelStyle}>Notifications (optional)</label>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <input
                    value={ntfyTopic}
                    onChange={e => setNtfyTopic(e.target.value)}
                    placeholder="Ntfy topic (e.g. transcription-alerts)"
                    style={inputStyle}
                  />
                  <input
                    value={discordWebhook}
                    onChange={e => setDiscordWebhook(e.target.value)}
                    placeholder="Discord webhook URL"
                    style={inputStyle}
                  />
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    <input
                      value={pushoverUser}
                      onChange={e => setPushoverUser(e.target.value)}
                      placeholder="Pushover user key"
                      style={inputStyle}
                    />
                    <input
                      value={pushoverToken}
                      onChange={e => setPushoverToken(e.target.value)}
                      placeholder="Pushover app token"
                      style={inputStyle}
                    />
                  </div>
                </div>
              </div>
```

### 3c. Include notification and priority data in the create profile request

Find where the create profile API call builds its request body (the `handleSubmit` or similar function):

Where the request body is built, make sure `priority` and `notifications` are included. The body should include:

```javascript
        priority: priority,
        notifications: (ntfyTopic || discordWebhook || pushoverUser) ? {
          ntfy_topic: ntfyTopic || undefined,
          discord_webhook: discordWebhook || undefined,
          pushover_user: pushoverUser || undefined,
          pushover_token: pushoverToken || undefined,
        } : undefined,
```

---

## CHANGE 4: Prompt Dry-Run Button

Add a dry-run test button to the profile stage editor. In the profile detail or stage prompt editor area, add a button that opens a small test panel.

In `ControlHub.jsx`, add this component before the main export:

```jsx
function DryRunPanel({ profileId, stageIndex, stageName, onClose }) {
  const [transcript, setTranscript] = useState("");
  const [jobId, setJobId] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [jobs, setAvailableJobs] = useState([]);

  useEffect(() => {
    apiFetch("/api/jobs?status=COMPLETE&limit=10")
      .then(data => setAvailableJobs(data?.jobs || []))
      .catch(() => {});
  }, []);

  const runTest = async () => {
    setLoading(true); setError(""); setResult(null);
    try {
      const body = { stage_index: stageIndex, max_chars: 3000 };
      if (jobId) body.job_id = jobId;
      else body.transcript = transcript;
      
      const data = await apiFetch(`/api/profiles/${profileId}/dry-run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      background: "rgba(0,0,0,0.5)", position: "fixed", inset: 0, zIndex: 1100,
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <div style={{
        background: "#12121f", borderRadius: 16, padding: 24, maxWidth: 700, width: "90%",
        maxHeight: "80vh", overflow: "auto", border: "1px solid rgba(255,255,255,0.08)",
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h3 style={{ color: "rgba(255,255,255,0.8)", margin: 0, fontSize: 16 }}>
            Dry Run: {stageName}
          </h3>
          <button onClick={onClose} style={{
            background: "none", border: "none", color: "rgba(255,255,255,0.3)", fontSize: 18, cursor: "pointer"
          }}>✕</button>
        </div>

        {/* Input source */}
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", display: "block", marginBottom: 4 }}>
            From a previous job:
          </label>
          <select
            value={jobId}
            onChange={e => { setJobId(e.target.value); if (e.target.value) setTranscript(""); }}
            style={{
              width: "100%", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 8, color: "rgba(255,255,255,0.6)", fontSize: 12, padding: "6px 10px", outline: "none",
            }}
          >
            <option value="" style={{ background: "#1a1a2e" }}>— Or paste text below —</option>
            {jobs.map(j => (
              <option key={j.id} value={j.id} style={{ background: "#1a1a2e" }}>
                {j.filename?.split("/").pop()} ({j.profile_id})
              </option>
            ))}
          </select>
        </div>

        {!jobId && (
          <div style={{ marginBottom: 12 }}>
            <textarea
              value={transcript}
              onChange={e => setTranscript(e.target.value)}
              placeholder="Paste sample transcript here..."
              rows={6}
              style={{
                width: "100%", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: 8, color: "rgba(255,255,255,0.6)", fontSize: 12, padding: 10, outline: "none",
                fontFamily: "'JetBrains Mono', monospace", resize: "vertical",
              }}
            />
          </div>
        )}

        <button
          onClick={runTest}
          disabled={loading || (!transcript && !jobId)}
          style={{
            background: loading ? "rgba(255,255,255,0.05)" : "rgba(96,165,250,0.15)",
            border: "1px solid rgba(96,165,250,0.3)", borderRadius: 8,
            padding: "8px 20px", color: "#60a5fa", fontSize: 13, fontWeight: 600,
            cursor: loading ? "wait" : "pointer", marginBottom: 16,
          }}
        >
          {loading ? "Running..." : "Test Stage"}
        </button>

        {error && (
          <div style={{ color: "#f87171", fontSize: 12, marginBottom: 12, padding: 10, background: "rgba(248,113,113,0.05)", borderRadius: 8 }}>
            {error}
          </div>
        )}

        {result && (
          <div>
            <div style={{ display: "flex", gap: 16, marginBottom: 12, fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
              <span>Model: <strong style={{ color: "#a5b4fc" }}>{result.model}</strong></span>
              <span>Provider: {result.provider}</span>
              <span>Tokens: {((result.input_tokens + result.output_tokens) / 1000).toFixed(1)}k</span>
              <span>Cost: <strong style={{ color: "#34d399" }}>${result.cost.toFixed(4)}</strong></span>
            </div>
            <pre style={{
              background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 8, padding: 12, fontSize: 11, color: "rgba(255,255,255,0.6)",
              whiteSpace: "pre-wrap", maxHeight: 300, overflow: "auto",
              fontFamily: "'JetBrains Mono', monospace",
            }}>
              {result.output}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
```

### 4b. Add a "Test" button to stage items in ProfileDetail

In the ProfileDetail component where stages are listed, add a test button next to each stage. Find where stages are mapped and rendered, and add:

```jsx
<button
  onClick={(e) => { e.stopPropagation(); setDryRunStage({ index: i, name: stage.name }); }}
  style={{
    background: "rgba(96,165,250,0.08)", border: "1px solid rgba(96,165,250,0.2)",
    borderRadius: 6, padding: "2px 8px", fontSize: 10, color: "#60a5fa",
    cursor: "pointer", fontWeight: 500,
  }}
>
  Test
</button>
```

And add state for the dry-run panel at the top of ProfileDetail:
```javascript
const [dryRunStage, setDryRunStage] = useState(null);
```

And render the panel at the bottom of ProfileDetail's return:
```jsx
{dryRunStage && (
  <DryRunPanel
    profileId={profile.id}
    stageIndex={dryRunStage.index}
    stageName={dryRunStage.name}
    onClose={() => setDryRunStage(null)}
  />
)}
```

---

## CHANGE 5: Priority indicator on Profile Cards

In `ProfileCard`, update the stats line:

Find:
```jsx
            {profile.stage_count} stage{profile.stage_count !== 1 ? "s" : ""} · {jobCount} job{jobCount !== 1 ? "s" : ""}
```

Replace with:
```jsx
            {profile.stage_count} stage{profile.stage_count !== 1 ? "s" : ""} · {jobCount} job{jobCount !== 1 ? "s" : ""}
            {profile.priority && profile.priority !== 5 && (
              <span style={{ color: profile.priority <= 3 ? "rgba(251,191,36,0.5)" : "rgba(255,255,255,0.15)" }}>
                {" "}· P{profile.priority}
              </span>
            )}
            {profile.has_notifications && (
              <span style={{ color: "rgba(255,255,255,0.15)" }}> · 🔔</span>
            )}
```

---

## CHANGE 6: Priority on job rows

In the `JobRow` component, add priority badge near the status. Find the StatusBadge usage and add after it:

```jsx
{job.priority && job.priority !== 5 && (
  <span style={{
    fontSize: 9, fontWeight: 600, padding: "1px 5px", borderRadius: 4,
    background: job.priority <= 3 ? "rgba(251,191,36,0.1)" : "rgba(255,255,255,0.03)",
    color: job.priority <= 3 ? "#fbbf24" : "rgba(255,255,255,0.2)",
    border: `1px solid ${job.priority <= 3 ? "rgba(251,191,36,0.15)" : "rgba(255,255,255,0.03)"}`,
  }}>
    P{job.priority}
  </span>
)}
```

---

## Verification

After applying all frontend changes and rebuilding:

1. `cd frontend && npm run build`
2. `docker compose build app`
3. `docker compose up -d`

Test:
- **Stage tracker**: Submit a job → watch individual stages appear with ○→◌→✓ progression
- **Cost**: Hover over stage badges to see per-stage cost and token counts
- **Priority**: Create a profile with priority 2, submit jobs from different profiles → high priority job should process first
- **Notifications**: Create a profile with ntfy topic set, submit a job → check ntfy for notification
- **Dry-run**: Open a profile detail → click "Test" on a stage → paste sample text or pick a previous job → verify output
- **Profile cards**: Should show P{n} for non-default priority and 🔔 for notification-enabled profiles
