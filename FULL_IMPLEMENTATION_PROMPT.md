# Transcription Pipeline — Full Implementation Sprint

## Overview

This is a comprehensive implementation task for the transcription pipeline at `transcribe.delboysden.uk`. There are three parts:

1. **Frontend Update** — Deploy the updated `ControlHub.jsx` 
2. **Multi-Provider LLM Support** — Add OpenRouter, OpenAI, and Z.ai as processing providers
3. **Phase 4 Features** — WebSocket live updates, Syncthing integration, prompt editor, cost tracking, production hardening

Read `MULTI_PROVIDER_PROMPT.md` in the project root for the detailed multi-provider implementation spec. This prompt covers everything else plus integration points.

---

## PART 1: Frontend Update

The uploaded `ControlHub.jsx` has these changes vs what's currently deployed:
- Profiles now display in a horizontal grid (left-to-right) instead of a vertical stack
- "+ New Profile" button moved to a header bar above the profiles
- Delete profile button (red ✕ on hover) — only on YAML-backed profiles, not built-in types (meeting, supervision, client, lecture, braindump)
- Delete job button on each job row (hover to reveal ✕) — works for QUEUED, FAILED, COMPLETE, CANCELLED jobs
- Browser back button support — pressing back returns to dashboard instead of previous page
- Model dropdown in Create Profile modal expanded with: deepseek-chat, deepseek-reasoner, qwen-2.5-72b, claude-sonnet-4-20250514, claude-haiku-4-5-20251001, gpt-4o, gpt-4o-mini, gemini-2.0-flash, llama-3.3-70b
- Null safety for health/ready checks when API hasn't responded yet
- API_BASE set to "" (empty string) for relative URLs through Caddy proxy

### Steps:
1. Copy the uploaded `ControlHub.jsx` to `frontend/src/ControlHub.jsx`
2. Rebuild the frontend: `cd frontend && npm run build`
3. Restart the app container so FastAPI serves the new static files

---

## PART 2: Multi-Provider LLM Support

Read and implement everything in `MULTI_PROVIDER_PROMPT.md`. Key summary:

- Create `src/worker/providers.py` — provider registry with auto-detection from model names
- Add `provider` field to `ProcessingStage` in `src/worker/types.py`
- Refactor `_call_api()` in `src/worker/formatter.py` to accept a `provider_config` parameter
- Update `MultiStageFormatter.process_transcript()` to resolve provider per-stage
- Update `src/worker/processor.py` to not require DeepSeek specifically
- Update `src/worker/profile_loader.py` to parse `provider` from YAML
- Update `src/api/dependencies.py` — add new keys, fix `require_api_keys()` to only require Groq + at least one LLM
- Update `src/api/schemas.py` — add `provider` to stage info schemas
- Update `docker-compose.yml` — add `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ZAI_API_KEY` env vars
- Update `.env` with placeholder keys

Also update the Create Profile modal's model dropdown in the frontend to include a provider selector. Add a dropdown below the model selector in each stage card:

```jsx
// In CreateProfileModal, after the model <select>, add:
<div>
  <label style={labelStyle}>Provider</label>
  <select
    value={stage.provider || ""}
    onChange={e => updateStage(idx, "provider", e.target.value)}
    style={{ ...inputStyle, cursor: "pointer" }}
  >
    <option value="" style={{ background: "#1a1a2e" }}>Auto-detect</option>
    <option value="deepseek" style={{ background: "#1a1a2e" }}>DeepSeek (direct)</option>
    <option value="openrouter" style={{ background: "#1a1a2e" }}>OpenRouter</option>
    <option value="openai" style={{ background: "#1a1a2e" }}>OpenAI (direct)</option>
    <option value="zai" style={{ background: "#1a1a2e" }}>Z.ai</option>
  </select>
</div>
```

And include `provider` in the stage data passed to `handleSave`:
```javascript
stages: stages.map((s, i) => ({
  ...existingFields,
  provider: s.provider || "",  // Add this
})),
```

Update the stage default too:
```javascript
const [stages, setStages] = useState([
  { name: "Clean & Format", model: "deepseek-chat", provider: "", temperature: 0.3, max_tokens: 4096, prompt: "" },
]);
```

---

## PART 3: Phase 4 Features

### 3A. WebSocket Live Updates

Replace the 10-second polling with WebSocket push for real-time job status.

**Backend (`src/main.py` and new `src/api/websocket.py`):**

```python
# src/api/websocket.py
from fastapi import WebSocket, WebSocketDisconnect
from typing import Set
import json, logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()
    
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
        logger.info(f"WS connected. {len(self.active)} active")
    
    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
        logger.info(f"WS disconnected. {len(self.active)} active")
    
    async def broadcast(self, event: str, data: dict):
        msg = json.dumps({"event": event, "data": data})
        dead = set()
        for ws in self.active:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        self.active -= dead

manager = ConnectionManager()
```

In `src/main.py`, add the WebSocket endpoint:
```python
from src.api.websocket import manager

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

In the processor (`src/worker/processor.py`), after each stage completion and job status change, broadcast:
```python
# This is tricky because the worker runs in a separate process.
# Simplest approach: write status changes to Redis pub/sub,
# then have the API server subscribe and broadcast via WebSocket.

# In the worker, after updating job status:
import redis
r = redis.Redis(host="redis", port=6379)
r.publish("job_updates", json.dumps({
    "job_id": job.id,
    "status": job.status,
    "current_stage": job.current_stage,
    "error": job.error,
}))
```

In `src/main.py`, add a background task that subscribes to Redis and broadcasts:
```python
import asyncio, redis.asyncio as aioredis, json

async def redis_listener():
    r = aioredis.Redis(host="redis", port=6379)
    pubsub = r.pubsub()
    await pubsub.subscribe("job_updates")
    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            await manager.broadcast("job_update", data)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing startup ...
    task = asyncio.create_task(redis_listener())
    yield
    task.cancel()
    # ... existing shutdown ...
```

**Frontend — update ControlHub.jsx:**

Add WebSocket connection with automatic fallback to polling:
```javascript
// In the main ControlHub component, replace the polling useEffect:

useEffect(() => {
  // Initial load
  const load = async () => { /* existing fetch logic */ };
  load();

  // Try WebSocket
  let ws = null;
  let fallbackInterval = null;

  const connectWs = () => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
    
    ws.onmessage = (event) => {
      const { event: evt, data } = JSON.parse(event.data);
      if (evt === "job_update") {
        setJobs(prev => prev.map(j => j.id === data.job_id ? { ...j, ...data } : j));
      }
    };
    
    ws.onclose = () => {
      // Fallback to polling if WS drops
      if (!fallbackInterval) {
        fallbackInterval = setInterval(load, 10000);
      }
      // Reconnect after 5s
      setTimeout(connectWs, 5000);
    };
    
    ws.onopen = () => {
      // Kill polling if WS connects
      if (fallbackInterval) {
        clearInterval(fallbackInterval);
        fallbackInterval = null;
      }
    };
  };

  connectWs();

  return () => {
    ws?.close();
    if (fallbackInterval) clearInterval(fallbackInterval);
  };
}, []);
```

Don't forget to add `redis.asyncio` to requirements if not already present (`pip install redis[hiredis]` or add to `requirements.txt`).

Update the Caddy config to proxy WebSocket:
```
transcribe.delboysden.uk {
    handle /ws {
        reverse_proxy transcription-pipeline:8000
    }
    # ... existing handles ...
}
```

Caddy handles WebSocket upgrades automatically with `reverse_proxy`, but the `/ws` route should be explicitly listed.

### 3B. Syncthing Integration

Add a `syncthing_share` field to profiles so outputs are automatically routed to the right Syncthing folder.

**Profile YAML addition:**
```yaml
name: business_lecture
syncthing:
  share_folder: "keira-docs"     # Syncthing folder ID
  subfolder: "lectures"           # Optional subfolder within the share
```

**Backend changes:**

1. Add to `ProcessingStage` types or create a new `SyncthingConfig` dataclass:
```python
@dataclass
class SyncthingConfig:
    share_folder: str = ""
    subfolder: str = ""

@dataclass  
class DegreeProfile:
    name: str
    stages: List[ProcessingStage]
    skip_diarization: bool = False
    syncthing: Optional[SyncthingConfig] = None  # NEW
```

2. Update `ProfileLoader._parse_profile()` to read the syncthing config.

3. Update the processor to use the profile's syncthing config instead of hardcoded `user_subdir`:
```python
# In _process_with_profile, replace the hardcoded logic:
# OLD:
#   user_subdir = None
#   if profile_id == "business_lecture":
#       user_subdir = "keira"
# NEW:
profile = self.profile_loader.get_profile(profile_id)
syncthing = getattr(profile, 'syncthing', None)
user_subdir = syncthing.subfolder if syncthing else None
```

4. Add a Syncthing API client for the hub's System page. Syncthing has a REST API (default port 8384). Create `src/api/routes/syncthing.py`:

```python
import os, requests
from fastapi import APIRouter

router = APIRouter(prefix="/api/syncthing", tags=["Syncthing"])

SYNCTHING_URL = os.getenv("SYNCTHING_URL", "http://localhost:8384")
SYNCTHING_KEY = os.getenv("SYNCTHING_API_KEY", "")

@router.get("/status")
async def syncthing_status():
    """Get Syncthing system status."""
    if not SYNCTHING_KEY:
        return {"configured": False}
    try:
        r = requests.get(
            f"{SYNCTHING_URL}/rest/system/status",
            headers={"X-API-Key": SYNCTHING_KEY},
            timeout=5
        )
        return {"configured": True, "status": r.json()}
    except Exception as e:
        return {"configured": True, "error": str(e)}

@router.get("/folders")
async def syncthing_folders():
    """Get Syncthing folder status."""
    if not SYNCTHING_KEY:
        return {"configured": False, "folders": []}
    try:
        r = requests.get(
            f"{SYNCTHING_URL}/rest/system/config",
            headers={"X-API-Key": SYNCTHING_KEY},
            timeout=5
        )
        config = r.json()
        folders = []
        for f in config.get("folders", []):
            # Get completion for each folder
            comp = requests.get(
                f"{SYNCTHING_URL}/rest/db/completion?folder={f['id']}",
                headers={"X-API-Key": SYNCTHING_KEY},
                timeout=5
            ).json()
            folders.append({
                "id": f["id"],
                "label": f.get("label", f["id"]),
                "path": f["path"],
                "completion": comp.get("completion", 0),
                "state": "synced" if comp.get("completion", 0) >= 100 else "syncing",
            })
        return {"configured": True, "folders": folders}
    except Exception as e:
        return {"configured": True, "error": str(e), "folders": []}
```

Register in `src/main.py`:
```python
from src.api.routes.syncthing import router as syncthing_router
app.include_router(syncthing_router)
```

Add env vars to docker-compose.yml:
```yaml
- SYNCTHING_URL=${SYNCTHING_URL:-http://syncthing:8384}
- SYNCTHING_API_KEY=${SYNCTHING_API_KEY:-}
```

**Frontend — add Syncthing section to the System/Health page:**

In the ControlHub's system status view (or wherever health info is shown), add a Syncthing panel that fetches from `/api/syncthing/status` and `/api/syncthing/folders` showing folder sync status with progress bars. This is informational only — no need for controls.

Also add a "Syncthing" section to the Create Profile modal (step 1, after the skip diarization toggle):
```jsx
<div>
  <label style={labelStyle}>Output Syncthing Folder</label>
  <input
    value={syncthingFolder}
    onChange={e => setSyncthingFolder(e.target.value)}
    placeholder="e.g. keira-docs (leave blank for default)"
    style={inputStyle}
  />
</div>
<div>
  <label style={labelStyle}>Subfolder</label>
  <input
    value={syncthingSubfolder}
    onChange={e => setSyncthingSubfolder(e.target.value)}
    placeholder="e.g. lectures"
    style={inputStyle}
  />
</div>
```

### 3C. In-Browser Prompt Editor

Add the ability to view and edit prompt templates from the Control Hub.

**Backend — add prompt endpoints to profiles route:**

```python
@router.get("/{profile_id}/prompts/{stage_index}")
async def get_stage_prompt(profile_id: str, stage_index: int, ...):
    """Get the prompt content for a specific stage."""
    profile = profile_loader.get_profile(profile_id)
    if not profile or stage_index >= len(profile.stages):
        raise HTTPException(404, "Stage not found")
    stage = profile.stages[stage_index]
    return {"prompt": stage.prompt_template, "filename": stage.prompt_file}

@router.put("/{profile_id}/prompts/{stage_index}")  
async def update_stage_prompt(profile_id: str, stage_index: int, body: dict, ...):
    """Update the prompt content for a specific stage."""
    profile = profile_loader.get_profile(profile_id)
    if not profile or stage_index >= len(profile.stages):
        raise HTTPException(404, "Stage not found")
    stage = profile.stages[stage_index]
    prompt_path = Path("config/prompts") / stage.prompt_file
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(body["prompt"], encoding="utf-8")
    profile_loader.reload()
    return {"saved": True, "filename": stage.prompt_file}
```

**Frontend — add prompt editor to ProfileDetail view:**

When viewing a profile's detail page, each stage should have an "Edit Prompt" button. Clicking it opens a modal/panel with a textarea showing the current prompt content, with a Save button. Use a monospace font for the editor. The textarea should be tall (at least 400px) and resizable.

```jsx
// Prompt editor state
const [editingPrompt, setEditingPrompt] = useState(null); // { stageIndex, content, filename }

const loadPrompt = async (stageIndex) => {
  const data = await apiFetch(`/api/profiles/${profile.id}/prompts/${stageIndex}`);
  setEditingPrompt({ stageIndex, content: data.prompt, filename: data.filename });
};

const savePrompt = async () => {
  await apiFetch(`/api/profiles/${editingPrompt.stageIndex}/prompts/${editingPrompt.stageIndex}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: editingPrompt.content }),
  });
  setEditingPrompt(null);
};
```

### 3D. Cost Tracking Dashboard

Track and display costs per job, per profile, and over time.

**Backend — the `StageResult` model already has `input_tokens` and `output_tokens` fields.** 

1. Update `_call_api()` in the formatter to return token usage alongside the content:
```python
# After a successful API call, return both content and usage:
usage = data.get("usage", {})
return content, {
    "input_tokens": usage.get("prompt_tokens", 0),
    "output_tokens": usage.get("completion_tokens", 0),
    "model": model or self.model,
}
```

2. Update `MultiStageFormatter.process_transcript()` to capture this usage data and return it in results.

3. Update the processor's `_record_stage()` calls to include token counts.

4. Update `Job.cost_estimate` calculation based on actual token usage and model-specific pricing. Create a simple pricing lookup:
```python
# In providers.py or a new pricing.py
PRICING = {  # per 1M tokens [input, output]
    "deepseek-chat": [0.14, 0.28],
    "deepseek-reasoner": [0.55, 2.19],
    "gpt-4o": [2.50, 10.00],
    "gpt-4o-mini": [0.15, 0.60],
    "anthropic/claude-sonnet-4": [3.00, 15.00],
    "anthropic/claude-haiku-4.5": [0.80, 4.00],
}

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = PRICING.get(model, [1.0, 3.0])  # Default fallback
    return (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000
```

5. Add a cost summary endpoint:
```python
@router.get("/api/costs/summary")
async def cost_summary(session: Session = Depends(get_db_session)):
    jobs = session.exec(select(Job)).all()
    total_cost = sum(j.cost_estimate for j in jobs)
    by_profile = {}
    for j in jobs:
        by_profile.setdefault(j.profile_id, 0)
        by_profile[j.profile_id] += j.cost_estimate
    return {
        "total_cost": total_cost,
        "by_profile": by_profile,
        "job_count": len(jobs),
    }
```

**Frontend — add a cost section:**

On the dashboard, update the stats bar to show total cost. Optionally add a "Costs" tab/view showing:
- Total spend
- Spend by profile (bar chart or list)
- Average cost per job
- Cost trend (if enough data — list of recent job costs)

Use the existing glassmorphic card style.

### 3E. Production Hardening

1. **Static file serving** — should already be done (FastAPI serving `frontend/dist`). Verify it works.

2. **Rate limiting** — Add basic rate limiting to prevent abuse since the app is publicly accessible:
```python
# pip install slowapi
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# On upload endpoint:
@router.post("", ...)
@limiter.limit("10/minute")
async def create_job(request: Request, ...):
```

3. **Basic auth** — Add optional API key auth. Simple approach:
```python
# In dependencies.py
from fastapi import Security
from fastapi.security import APIKeyHeader

API_KEY = os.getenv("PIPELINE_API_KEY", "")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(key: str = Security(api_key_header)):
    if API_KEY and key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
```

Only enforce if `PIPELINE_API_KEY` is set — if it's empty, auth is disabled (for development).

Add `PIPELINE_API_KEY` to docker-compose env vars.

Update the frontend to include the API key in requests if configured — store it in a config or read from a meta tag.

4. **CORS** — Tighten from `allow_origins=["*"]` to:
```python
allow_origins=[
    "https://transcribe.delboysden.uk",
    "http://localhost:5173",
    "http://localhost:8888",
],
```

5. **Max upload size** — Already set to 500MB in `upload.py` but add nginx/Caddy level protection too. In Caddyfile:
```
transcribe.delboysden.uk {
    request_body {
        max_size 500MB
    }
    # ... existing handles ...
}
```

6. **Logging** — Add structured JSON logging for production:
```python
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        })
```

### 3F. Unit Tests

Create `tests/` directory with basic API tests. Use `pytest` and `httpx` for async testing.

```python
# tests/test_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] in ["healthy", "degraded"]

@pytest.mark.asyncio
async def test_ready(client):
    r = await client.get("/ready")
    assert r.status_code == 200
    assert "ready" in r.json()

@pytest.mark.asyncio
async def test_list_profiles(client):
    r = await client.get("/api/profiles")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

@pytest.mark.asyncio
async def test_list_jobs(client):
    r = await client.get("/api/jobs")
    assert r.status_code == 200
    assert "jobs" in r.json()

@pytest.mark.asyncio
async def test_create_job_no_file(client):
    r = await client.post("/api/jobs", data={"profile_id": "meeting"})
    assert r.status_code == 422  # Missing file

@pytest.mark.asyncio  
async def test_get_nonexistent_job(client):
    r = await client.get("/api/jobs/nonexistent-id")
    assert r.status_code == 404

@pytest.mark.asyncio
async def test_delete_nonexistent_job(client):
    r = await client.delete("/api/jobs/nonexistent-id")
    assert r.status_code == 404
```

Add to `requirements.txt`: `pytest`, `pytest-asyncio`, `httpx`

Add `pytest.ini` or section in `pyproject.toml`:
```ini
[tool:pytest]
asyncio_mode = auto
```

---

## Implementation Order

1. **Frontend update** (Part 1) — quick win, deploy immediately
2. **Multi-provider** (Part 2) — read and implement `MULTI_PROVIDER_PROMPT.md`, then the frontend provider dropdown
3. **WebSocket** (3A) — biggest UX improvement
4. **Cost tracking** (3D) — useful for monitoring spend across providers
5. **Prompt editor** (3C) — quality of life for iterating on prompts
6. **Syncthing** (3B) — output routing
7. **Production hardening** (3E) — auth, rate limiting, CORS
8. **Tests** (3F) — safety net

Don't rebuild or restart until all changes for a given part are reviewed. Present each part for review before moving to the next.
