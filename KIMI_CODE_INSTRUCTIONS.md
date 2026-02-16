# Transcription Pipeline — Complete Fix Implementation

You are working on a transcription pipeline project. Apply ALL of the following changes in order. Do not skip any steps.

## Context

This is a FastAPI + React transcription pipeline. The repo structure has:
- Backend: `src/api/routes/`, `src/api/dependencies.py`, `src/worker/profile_loader.py`, `src/main.py`
- Frontend: `frontend/src/ControlHub.jsx`, `frontend/src/App.jsx`

---

## CHANGE 1: Fix `src/worker/profile_loader.py`

Three bugs to fix in this file:

### 1a. In `reload()`, clear `_profiles` before reloading so deleted profiles don't persist:

Find:
```python
    def reload(self):
        """Reload all profiles and configuration."""
        logger.info("Reloading profiles and configuration...")
        self._load_folder_map()
        self._load_profiles()
```

Replace with:
```python
    def reload(self):
        """Reload all profiles and configuration."""
        logger.info("Reloading profiles and configuration...")
        self._profiles = {}
        self._load_folder_map()
        self._load_profiles()
```

### 1b. In `_load_profiles()`, extract profile_id from the filename stem and pass it to `_parse_profile()`:

Find:
```python
            try:
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f)
                    self._parse_profile(data)
```

Replace with:
```python
            try:
                profile_id = yaml_file.stem
                
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f)
                    self._parse_profile(data, profile_id)
```

### 1c. Change `_parse_profile` to accept `profile_id` and use it as the dict key:

Find:
```python
    def _parse_profile(self, data: Dict[str, Any]):
        """Parse a single profile dictionary into a DegreeProfile object."""
```

Replace with:
```python
    def _parse_profile(self, data: Dict[str, Any], profile_id: str):
        """Parse a single profile dictionary into a DegreeProfile object."""
```

Find:
```python
        self._profiles[profile_name] = profile
        logger.info(f"Loaded profile: {profile_name} with {len(stages)} stages")
```

Replace with:
```python
        self._profiles[profile_id] = profile
        logger.info(f"Loaded profile: {profile_id} ({profile_name}) with {len(stages)} stages")
```

### 1d. In `_parse_profile`, make syncthing config accept both `share_folder` and `folder` keys:

Find:
```python
            syncthing = SyncthingConfig(
                share_folder=syncthing_data.get("share_folder", ""),
                subfolder=syncthing_data.get("subfolder", ""),
            )
```

Replace with:
```python
            syncthing = SyncthingConfig(
                share_folder=syncthing_data.get("share_folder", syncthing_data.get("folder", "")),
                subfolder=syncthing_data.get("subfolder", ""),
            )
```

---

## CHANGE 2: Fix `src/api/dependencies.py`

Replace the `get_profile_loader` function with a singleton pattern. The current code creates a new ProfileLoader (re-reading all YAML from disk) on every single API request.

Find:
```python
def get_profile_loader() -> ProfileLoader:
    """Dependency to get ProfileLoader instance."""
    config_dir = Path("config").resolve()
    return ProfileLoader(config_dir)
```

Replace with:
```python
_profile_loader: Optional[ProfileLoader] = None


def get_profile_loader() -> ProfileLoader:
    """Dependency to get ProfileLoader singleton instance."""
    global _profile_loader
    if _profile_loader is None:
        config_dir = Path("config").resolve()
        _profile_loader = ProfileLoader(config_dir)
    return _profile_loader
```

Make sure `Optional` is already imported from `typing` at the top of the file (it should be).

---

## CHANGE 3: Fix `src/api/routes/profiles.py`

### 3a. Add logging import at the top:

Add after the existing imports:
```python
import logging
logger = logging.getLogger(__name__)
```

### 3b. Fix path resolution in `create_profile` — use profile_loader paths instead of relative `Path("config")`:

Find:
```python
    # 4. Write YAML to config/profiles/{request.id}.yaml
    config_dir = Path("config")
    profiles_dir = config_dir / "profiles"
    prompts_dir = config_dir / "prompts"
```

Replace with:
```python
    # 4. Write YAML to config/profiles/{request.id}.yaml
    profiles_dir = profile_loader.profiles_dir
    prompts_dir = profile_loader.prompts_dir
```

### 3c. Add diagnostic logging when profile fails to load after creation:

Find:
```python
        profile = profile_loader.get_profile(request.id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Profile created but failed to load"
            )
```

Replace with:
```python
        profile = profile_loader.get_profile(request.id)
        if not profile:
            logger.error(
                f"Profile created but failed to load. "
                f"request.id='{request.id}', "
                f"available profiles: {list(profile_loader._profiles.keys())}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Profile created but failed to load"
            )
```

### 3d. Fix path resolution in `update_stage_prompt`:

Find:
```python
    prompt_path = Path("config/prompts") / stage.prompt_file
```

Replace with:
```python
    prompt_path = profile_loader.prompts_dir / stage.prompt_file
```

### 3e. Add guard against deleting built-in profiles in `delete_profile`:

Add at the very start of the `delete_profile` function body, before the existing profile existence check:
```python
    # Prevent deletion of standard types
    standard_types = ["meeting", "supervision", "client", "lecture", "braindump"]
    if profile_id in standard_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete built-in profile '{profile_id}'"
        )
```

---

## CHANGE 4: Fix `src/api/routes/jobs.py` — Ghost job deletion

Replace the entire `delete_job` function with this version that actually removes jobs from the DB:

Find the entire `delete_job` function (from `@router.delete` to `return None`) and replace with:

```python
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
```

Also add `import logging` at the top and `logger = logging.getLogger(__name__)` after the imports if not already present.

---

## CHANGE 5: Create new file `src/api/routes/logs.py`

Create this entirely new file for the log streaming API:

```python
"""
Log streaming API routes.

Provides real-time log access via Server-Sent Events (SSE) and
recent log retrieval for the Control Hub log console.
"""

import asyncio
import json
import logging
import os
import shutil
from collections import deque
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/logs", tags=["Logs"])

LOG_BUFFER_SIZE = 500
log_buffer: deque = deque(maxlen=LOG_BUFFER_SIZE)
log_subscribers: list[asyncio.Queue] = []


class WebLogHandler(logging.Handler):
    """Custom logging handler that captures logs for the web console."""
    
    def emit(self, record):
        try:
            entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
            }
            log_buffer.append(entry)
            
            dead_queues = []
            for queue in log_subscribers:
                try:
                    queue.put_nowait(entry)
                except asyncio.QueueFull:
                    pass
                except Exception:
                    dead_queues.append(queue)
            
            for q in dead_queues:
                if q in log_subscribers:
                    log_subscribers.remove(q)
                    
        except Exception:
            self.handleError(record)


def install_log_handler():
    """Install the WebLogHandler on the root logger. Call once during app startup."""
    handler = WebLogHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))
    
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    
    for name in ["src", "uvicorn", "uvicorn.access", "worker", "src.worker", "src.api"]:
        logger = logging.getLogger(name)
        logger.propagate = True


@router.get("/recent")
async def get_recent_logs(
    limit: int = Query(100, ge=1, le=500),
    level: Optional[str] = Query(None),
    logger_name: Optional[str] = Query(None),
):
    """Get recent log entries from the in-memory buffer."""
    entries = list(log_buffer)
    
    if level:
        level_upper = level.upper()
        level_priority = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_priority = level_priority.get(level_upper, 0)
        entries = [e for e in entries if level_priority.get(e["level"], 0) >= min_priority]
    
    if logger_name:
        entries = [e for e in entries if e["logger"].startswith(logger_name)]
    
    return {
        "entries": entries[-limit:],
        "total_buffered": len(log_buffer),
        "buffer_size": LOG_BUFFER_SIZE,
    }


@router.get("/stream")
async def stream_logs(
    level: Optional[str] = Query(None),
):
    """Stream logs in real-time via Server-Sent Events (SSE)."""
    
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    log_subscribers.append(queue)
    
    level_priority = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    min_priority = level_priority.get((level or "").upper(), 0)
    
    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'buffered': len(log_buffer)})}\n\n"
            
            while True:
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if level_priority.get(entry.get("level", ""), 0) >= min_priority:
                        yield f"data: {json.dumps(entry)}\n\n"
                except asyncio.TimeoutError:
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in log_subscribers:
                log_subscribers.remove(queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/system")
async def get_system_info():
    """Get system information useful for debugging."""
    disk = shutil.disk_usage(".")
    
    return {
        "timestamp": datetime.now().isoformat(),
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
        },
        "environment": {
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "groq_configured": bool(os.getenv("GROQ_API_KEY")),
            "deepseek_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
            "openrouter_configured": bool(os.getenv("OPENROUTER_API_KEY")),
        },
        "log_buffer": {
            "entries": len(log_buffer),
            "max_size": LOG_BUFFER_SIZE,
            "subscribers": len(log_subscribers),
        },
    }
```

---

## CHANGE 6: Update `src/main.py` — Register logs router

### 6a. After the line that includes the costs router, add:

Find:
```python
from src.api.routes.costs import router as costs_router
app.include_router(costs_router)
```

Add immediately after:
```python
from src.api.routes.logs import router as logs_router, install_log_handler
app.include_router(logs_router)
```

### 6b. Inside the `lifespan()` async context manager, add `install_log_handler()` after the directory creation loop and BEFORE the redis_task creation:

Find:
```python
    for directory in ["uploads", "processing", "output", "data", "logs"]:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    # Start Redis listener for WebSocket broadcasting
```

Replace with:
```python
    for directory in ["uploads", "processing", "output", "data", "logs"]:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    # Install web log handler for the log console
    install_log_handler()
    
    # Start Redis listener for WebSocket broadcasting
```

---

## CHANGE 7: Create new file `frontend/src/LogConsole.jsx`

Create the file `frontend/src/LogConsole.jsx` with the full LogConsole component. This is a real-time log viewer that connects to the backend via Server-Sent Events.

```jsx
import { useState, useEffect, useRef, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_URL || '';

async function apiFetch(path, options = {}) {
  const apiKey = document.querySelector('meta[name="api-key"]')?.content;
  if (apiKey) {
    options.headers = { ...options.headers, "X-API-Key": apiKey };
  }
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `API error: ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

const LEVEL_COLORS = {
  DEBUG: { color: "#6b7280", bg: "rgba(107,114,128,0.1)" },
  INFO: { color: "#60a5fa", bg: "rgba(96,165,250,0.1)" },
  WARNING: { color: "#fbbf24", bg: "rgba(251,191,36,0.1)" },
  ERROR: { color: "#f87171", bg: "rgba(248,113,113,0.1)" },
  CRITICAL: { color: "#ef4444", bg: "rgba(239,68,68,0.15)" },
};

function LogEntry({ entry }) {
  const levelCfg = LEVEL_COLORS[entry.level] || LEVEL_COLORS.INFO;
  const time = new Date(entry.timestamp).toLocaleTimeString("en-GB", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "68px 58px 1fr",
      gap: 8,
      padding: "3px 12px",
      fontSize: 12,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SF Mono', monospace",
      lineHeight: 1.6,
      borderBottom: "1px solid rgba(255,255,255,0.02)",
      background: entry.level === "ERROR" || entry.level === "CRITICAL"
        ? "rgba(248,113,113,0.03)" : "transparent",
    }}>
      <span style={{ color: "rgba(255,255,255,0.25)" }}>{time}</span>
      <span style={{
        color: levelCfg.color,
        background: levelCfg.bg,
        padding: "0 6px",
        borderRadius: 3,
        fontSize: 10,
        fontWeight: 600,
        textAlign: "center",
        letterSpacing: 0.3,
        alignSelf: "start",
        marginTop: 2,
      }}>
        {entry.level}
      </span>
      <span style={{
        color: entry.level === "ERROR" ? "#fca5a5" :
               entry.level === "WARNING" ? "#fde68a" :
               "rgba(255,255,255,0.65)",
        wordBreak: "break-word",
      }}>
        {entry.logger !== "root" && (
          <span style={{ color: "rgba(255,255,255,0.2)", marginRight: 6 }}>
            [{entry.logger}]
          </span>
        )}
        {entry.message}
      </span>
    </div>
  );
}

export default function LogConsole() {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [logs, setLogs] = useState([]);
  const [streaming, setStreaming] = useState(true);
  const [levelFilter, setLevelFilter] = useState("INFO");
  const [searchFilter, setSearchFilter] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const [connected, setConnected] = useState(false);
  const [errorCount, setErrorCount] = useState(0);

  const logEndRef = useRef(null);
  const scrollContainerRef = useRef(null);
  const eventSourceRef = useRef(null);

  useEffect(() => {
    if (autoScroll && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll]);

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
    setAutoScroll(atBottom);
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    apiFetch(`/api/logs/recent?limit=200&level=${levelFilter}`)
      .then(data => {
        if (data?.entries) {
          setLogs(data.entries);
          setErrorCount(data.entries.filter(e => e.level === "ERROR" || e.level === "CRITICAL").length);
        }
      })
      .catch(err => console.warn("Failed to load logs:", err));
  }, [isOpen, levelFilter]);

  useEffect(() => {
    if (!isOpen || !streaming) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
        setConnected(false);
      }
      return;
    }

    const url = `${API_BASE}/api/logs/stream?level=${levelFilter}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => setConnected(true);
    
    es.onmessage = (event) => {
      try {
        const entry = JSON.parse(event.data);
        if (entry.type === "connected") return;
        
        setLogs(prev => {
          const updated = [...prev, entry];
          return updated.length > 1000 ? updated.slice(-800) : updated;
        });

        if (entry.level === "ERROR" || entry.level === "CRITICAL") {
          setErrorCount(prev => prev + 1);
        }
      } catch (e) {}
    };

    es.onerror = () => setConnected(false);

    return () => {
      es.close();
      eventSourceRef.current = null;
      setConnected(false);
    };
  }, [isOpen, streaming, levelFilter]);

  const filteredLogs = searchFilter
    ? logs.filter(l => l.message.toLowerCase().includes(searchFilter.toLowerCase()) ||
                       l.logger.toLowerCase().includes(searchFilter.toLowerCase()))
    : logs;

  const clearLogs = () => { setLogs([]); setErrorCount(0); };

  const panelHeight = isExpanded ? "65vh" : 320;

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        style={{
          position: "fixed", bottom: 16, right: 16, zIndex: 999,
          display: "flex", alignItems: "center", gap: 6,
          padding: "8px 14px",
          background: "rgba(15,15,25,0.9)",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 10,
          color: "rgba(255,255,255,0.5)",
          fontSize: 12, fontWeight: 500, cursor: "pointer",
          backdropFilter: "blur(12px)",
          fontFamily: "'DM Sans', sans-serif",
          transition: "all 0.2s",
        }}
        onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(96,165,250,0.3)"; e.currentTarget.style.color = "#60a5fa"; }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)"; e.currentTarget.style.color = "rgba(255,255,255,0.5)"; }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="4 17 10 11 4 5" /><line x1="12" y1="19" x2="20" y2="19" />
        </svg>
        Logs
        {errorCount > 0 && (
          <span style={{
            background: "rgba(248,113,113,0.2)", color: "#f87171",
            fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 8,
          }}>
            {errorCount}
          </span>
        )}
      </button>
    );
  }

  return (
    <div style={{
      position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 1000,
      height: panelHeight, display: "flex", flexDirection: "column",
      background: "rgba(8,8,16,0.97)",
      borderTop: "1px solid rgba(255,255,255,0.08)",
      backdropFilter: "blur(20px)",
      transition: "height 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
    }}>
      {/* Toolbar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "6px 12px", borderBottom: "1px solid rgba(255,255,255,0.06)", flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{
              width: 6, height: 6, borderRadius: "50%",
              background: connected ? "#34d399" : "#f87171",
              boxShadow: connected ? "0 0 6px rgba(52,211,153,0.5)" : "0 0 6px rgba(248,113,113,0.5)",
            }} />
            <span style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.4)", fontFamily: "'DM Sans', sans-serif" }}>
              Log Console
            </span>
          </div>

          <select
            value={levelFilter}
            onChange={e => setLevelFilter(e.target.value)}
            style={{
              background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 6, color: "rgba(255,255,255,0.6)", fontSize: 11,
              padding: "3px 8px", outline: "none", cursor: "pointer", fontFamily: "'DM Sans', sans-serif",
            }}
          >
            <option value="DEBUG" style={{ background: "#0e0e1a" }}>DEBUG</option>
            <option value="INFO" style={{ background: "#0e0e1a" }}>INFO</option>
            <option value="WARNING" style={{ background: "#0e0e1a" }}>WARNING</option>
            <option value="ERROR" style={{ background: "#0e0e1a" }}>ERROR</option>
          </select>

          <input
            type="text" value={searchFilter}
            onChange={e => setSearchFilter(e.target.value)}
            placeholder="Filter..."
            style={{
              background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 6, color: "rgba(255,255,255,0.6)", fontSize: 11,
              padding: "3px 10px", outline: "none", width: 150,
              fontFamily: "'JetBrains Mono', monospace",
            }}
          />

          <span style={{ fontSize: 10, color: "rgba(255,255,255,0.2)" }}>
            {filteredLogs.length} entries
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <button
            onClick={() => setStreaming(!streaming)}
            style={{
              background: streaming ? "rgba(52,211,153,0.1)" : "rgba(251,191,36,0.1)",
              border: `1px solid ${streaming ? "rgba(52,211,153,0.2)" : "rgba(251,191,36,0.2)"}`,
              borderRadius: 6, padding: "4px 8px",
              color: streaming ? "#34d399" : "#fbbf24",
              cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
              fontSize: 10, fontWeight: 600,
            }}
          >
            {streaming ? "⏸ Live" : "▶ Paused"}
          </button>

          <button onClick={clearLogs} title="Clear logs" style={{
            background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 6, padding: "4px 8px", color: "rgba(255,255,255,0.3)",
            cursor: "pointer", fontSize: 11,
          }}>🗑</button>

          <button onClick={() => setIsExpanded(!isExpanded)} style={{
            background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 6, padding: "4px 8px", color: "rgba(255,255,255,0.3)",
            cursor: "pointer", fontSize: 11,
          }}>{isExpanded ? "▼" : "▲"}</button>

          <button onClick={() => setIsOpen(false)} style={{
            background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 6, padding: "4px 10px", color: "rgba(255,255,255,0.3)",
            cursor: "pointer", fontSize: 12, fontWeight: 600,
          }}>✕</button>
        </div>
      </div>

      {/* Log entries */}
      <div ref={scrollContainerRef} onScroll={handleScroll}
        style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>
        {filteredLogs.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center", color: "rgba(255,255,255,0.15)", fontSize: 12, fontFamily: "'DM Sans', sans-serif" }}>
            {connected ? "Waiting for log entries..." : "Connecting to log stream..."}
          </div>
        ) : (
          filteredLogs.map((entry, i) => (
            <LogEntry key={`${entry.timestamp}-${i}`} entry={entry} />
          ))
        )}
        <div ref={logEndRef} />
      </div>

      {!autoScroll && (
        <button
          onClick={() => { setAutoScroll(true); logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }}
          style={{
            position: "absolute", bottom: 8, right: 16,
            background: "rgba(96,165,250,0.15)", border: "1px solid rgba(96,165,250,0.3)",
            borderRadius: 8, padding: "4px 12px", color: "#60a5fa",
            fontSize: 11, fontWeight: 500, cursor: "pointer", fontFamily: "'DM Sans', sans-serif",
          }}
        >
          ↓ Jump to latest
        </button>
      )}

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap');
      `}</style>
    </div>
  );
}
```

---

## CHANGE 8: Update `frontend/src/ControlHub.jsx` — Add LogConsole

### 8a. Add import at the top of the file, after the existing React import:

```jsx
import LogConsole from "./LogConsole";
```

### 8b. Add the LogConsole component inside the render. Find the `{/* Global styles */}` comment (or the `<style>{` tag near the end of the component's return). Add `<LogConsole />` just BEFORE that style tag:

Find:
```jsx
      {/* Global styles */}
      <style>{`
```

Add immediately before it:
```jsx
      {/* Log Console */}
      <LogConsole />

      {/* Global styles */}
      <style>{`
```

---

## CHANGE 9: Update `src/api/routes/__init__.py` — Export logs router

Find:
```python
from src.api.routes.jobs import router as jobs_router
from src.api.routes.profiles import router as profiles_router

__all__ = ["jobs_router", "profiles_router"]
```

Replace with:
```python
from src.api.routes.jobs import router as jobs_router
from src.api.routes.profiles import router as profiles_router
from src.api.routes.logs import router as logs_router

__all__ = ["jobs_router", "profiles_router", "logs_router"]
```

---

## Verification

After applying all changes:

1. Run `cd frontend && npm run build` to rebuild the frontend
2. Run `docker compose build app worker` to rebuild the backend
3. Run `docker compose up -d` to restart

Test profile creation, job deletion, and check the log console button in the bottom-right corner of the UI.
