# Security Audit & Fixes

Apply all changes in order.

---

## FINDING 1: No Authentication on Most Routes (HIGH)

**Issue:** `verify_api_key` exists in dependencies.py but is NOT used on any route. The only auth check is `require_api_keys` on the `create_job` endpoint — and that checks whether the *server* has API keys configured, not whether the *request* is authorised. Every endpoint is wide open:

- `/api/profiles` — anyone can create/delete profiles
- `/api/profiles/{id}/dry-run` — anyone can burn your LLM tokens
- `/api/profiles/{id}/prompts/{n}` — anyone can read/overwrite your prompts
- `/api/jobs` — anyone can list/delete all jobs
- `/api/logs/stream` — anyone can read your server logs
- `/api/logs/system` — exposes disk usage and API key configuration status
- `/api/syncthing/*` — exposes your Syncthing folder structure and device IDs
- `/api/costs/summary` — exposes your spending data
- `/ws` — anyone can subscribe to real-time job updates

**Fix:** Add a lightweight API key middleware that protects all `/api/*` routes. Since this is a family tool behind Caddy on a Tailscale network (not a public SaaS), a single shared API key is appropriate.

### 1a. Add auth middleware to main.py

In `src/main.py`, add this middleware AFTER the CORS middleware and BEFORE the router includes:

Find:
```python
# Slowapi rate limiting error handler
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

Add BEFORE that block:
```python
# API key authentication middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class APIKeyMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key header on all /api/ routes when PIPELINE_API_KEY is set."""
    
    OPEN_PATHS = {"/health", "/ready", "/ws", "/docs", "/openapi.json", "/redoc"}
    
    async def dispatch(self, request, call_next):
        api_key = os.getenv("PIPELINE_API_KEY", "")
        
        # Skip auth if no key is configured (dev mode)
        if not api_key:
            return await call_next(request)
        
        path = request.url.path
        
        # Skip auth for non-API routes (frontend static files, health, websocket)
        if not path.startswith("/api/"):
            return await call_next(request)
        
        # Check the key
        request_key = request.headers.get("x-api-key", "")
        if request_key != api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
        
        return await call_next(request)

app.add_middleware(APIKeyMiddleware)
```

### 1b. Update the frontend to send the API key

The frontend needs to include `X-API-Key` in requests. The cleanest approach is to read it from a Vite env variable.

In `frontend/src/api/client.js`, update the `api` object methods to include the header:

Find:
```javascript
    async getJobs(params = {}) {
        const query = new URLSearchParams(params).toString();
        const url = `${API_BASE}/api/jobs${query ? `?${query}` : ''}`;
        const response = await fetch(url);
```

The simplest fix: add a helper function at the top of client.js and use it everywhere:

```javascript
const API_KEY = import.meta.env.VITE_PIPELINE_API_KEY || '';

function authHeaders(extra = {}) {
    const headers = { ...extra };
    if (API_KEY) headers['X-API-Key'] = API_KEY;
    return headers;
}
```

Then update every `fetch` call in the file to include `headers: authHeaders()`. For example:

```javascript
    async getJobs(params = {}) {
        const query = new URLSearchParams(params).toString();
        const url = `${API_BASE}/api/jobs${query ? `?${query}` : ''}`;
        const response = await fetch(url, { headers: authHeaders() });
```

Do this for ALL methods in the api object: `getJobs`, `getJob`, `createJob`, `deleteJob`, `getProfiles`, `getProfile`, `getHealth`.

For `createJob` which uses FormData:
```javascript
    async createJob(file, profileId) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('profile_id', profileId);

        const response = await fetch(`${API_BASE}/api/jobs`, {
            method: 'POST',
            headers: authHeaders(),  // Don't set Content-Type - browser sets it for FormData
            body: formData,
        });
```

### 1c. Also update `apiFetch` in ControlHub.jsx (if it has its own fetch helper)

Find any `apiFetch` function in ControlHub.jsx and update it similarly:

```javascript
const API_KEY = import.meta.env.VITE_PIPELINE_API_KEY || '';

async function apiFetch(path, options = {}) {
  if (API_KEY) {
    options.headers = { ...options.headers, "X-API-Key": API_KEY };
  }
  // ... rest of function
}
```

Do the same in `LogConsole.jsx` if it has its own `apiFetch`.

### 1d. Add the key to your frontend .env

Create/update `frontend/.env`:
```
VITE_PIPELINE_API_KEY=your-pipeline-api-key-here
```

Make sure this is in `.gitignore`:
```
frontend/.env
frontend/.env.local
```

### 1e. Set the key in docker-compose.yml

The `PIPELINE_API_KEY` env var is already in docker-compose.yml. Make sure it's set in your `.env` file on the server.

---

## FINDING 2: Path Traversal in Upload Handler (HIGH)

**Issue:** `profile_id` from user input is used directly to build the upload directory path:
```python
upload_dir = base_dir / profile_id
```
A malicious `profile_id` like `../../etc` would create directories outside the intended upload area. Same issue with `original_name` from the uploaded filename — `Path(file.filename).stem` doesn't sanitize for path separators.

**Fix:** Sanitize both `profile_id` and the filename.

In `src/api/upload.py`:

Find:
```python
    # Create upload directory
    upload_dir = base_dir / profile_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    original_name = Path(file.filename).stem
    extension = Path(file.filename).suffix
    unique_filename = f"{timestamp}_{original_name}{extension}"
```

Replace with:
```python
    import re
    
    # Sanitize profile_id to prevent path traversal
    safe_profile_id = re.sub(r'[^a-zA-Z0-9_-]', '', profile_id)
    if not safe_profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid profile_id"
        )
    
    # Create upload directory
    upload_dir = base_dir / safe_profile_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitize filename to prevent path traversal
    original_name = re.sub(r'[^a-zA-Z0-9_\- ]', '', Path(file.filename).stem)
    extension = Path(file.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        extension = ".bin"  # Fallback
    
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    unique_filename = f"{timestamp}_{original_name[:100]}{extension}"
    
    # Verify the final path is within the upload directory
    file_path = (upload_dir / unique_filename).resolve()
    if not str(file_path).startswith(str(base_dir.resolve())):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path"
        )
```

---

## FINDING 3: Path Traversal in Prompt File Writes (HIGH)

**Issue:** The `prompt_file` field from profile creation and the `update_stage_prompt` endpoint write files to disk using user-supplied paths:
```python
prompt_path = profile_loader.prompts_dir / stage.prompt_file
prompt_path.parent.mkdir(parents=True, exist_ok=True)
prompt_path.write_text(...)
```
A malicious `prompt_file` like `../../src/main.py` could overwrite any file the process can write to.

**Fix:** Validate that the resolved path stays within the prompts directory.

In `src/api/routes/profiles.py`, add a helper function near the top (after imports):

```python
def _safe_prompt_path(prompts_dir: Path, prompt_file: str) -> Path:
    """Resolve a prompt file path and verify it's within the prompts directory."""
    # Sanitize: no absolute paths, no parent traversal
    if prompt_file.startswith("/") or ".." in prompt_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid prompt_file path: {prompt_file}"
        )
    
    resolved = (prompts_dir / prompt_file).resolve()
    if not str(resolved).startswith(str(prompts_dir.resolve())):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Prompt file path escapes config directory"
        )
    return resolved
```

Then use it in `create_profile`:

Find:
```python
                prompt_path = prompts_dir / stage.prompt_file
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
```

Replace with:
```python
                prompt_path = _safe_prompt_path(prompts_dir, stage.prompt_file)
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
```

And in `update_stage_prompt`:

Find:
```python
    prompt_path = profile_loader.prompts_dir / stage.prompt_file
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(body.get("prompt", ""), encoding="utf-8")
```

Replace with:
```python
    prompt_path = _safe_prompt_path(profile_loader.prompts_dir, stage.prompt_file)
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(body.get("prompt", ""), encoding="utf-8")
```

---

## FINDING 4: File Size Not Actually Checked (MEDIUM)

**Issue:** `MAX_FILE_SIZE` is defined but never checked. The `validate_audio_file` function only checks the extension, not the size. A 10GB file would be accepted and written to disk.

**Fix:** Add size checking to the upload handler.

In `src/api/upload.py`, in `save_uploaded_file`, add a size check after saving:

Find (at the end of `save_uploaded_file`):
```python
    # Save file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    finally:
        file.file.close()
    
    return file_path.resolve()
```

Replace with:
```python
    # Save file with size limit enforcement
    try:
        bytes_written = 0
        with open(file_path, "wb") as buffer:
            while chunk := file.file.read(1024 * 1024):  # Read 1MB at a time
                bytes_written += len(chunk)
                if bytes_written > MAX_FILE_SIZE:
                    buffer.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    finally:
        file.file.close()
    
    return file_path.resolve()
```

---

## FINDING 5: WebSocket Has No Authentication (MEDIUM)

**Issue:** The `/ws` WebSocket endpoint accepts any connection. Anyone who knows the URL can subscribe to real-time job updates including job IDs, profile IDs, stage status, and error messages.

**Fix:** Add token-based auth to the WebSocket handshake.

In `src/main.py`, update the WebSocket endpoint:

Find:
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time job updates."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

Replace with:
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time job updates."""
    # Check API key if configured
    api_key = os.getenv("PIPELINE_API_KEY", "")
    if api_key:
        # Accept key via query param: /ws?key=xxx
        client_key = websocket.query_params.get("key", "")
        if client_key != api_key:
            await websocket.close(code=4001, reason="Unauthorized")
            return
    
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

Then update the frontend WebSocket connection in `ControlHub.jsx` to include the key:

Find the WebSocket connection code (something like):
```javascript
const ws = new WebSocket(`${wsUrl}/ws`);
```

Replace with:
```javascript
const apiKey = import.meta.env.VITE_PIPELINE_API_KEY || '';
const wsKeyParam = apiKey ? `?key=${encodeURIComponent(apiKey)}` : '';
const ws = new WebSocket(`${wsUrl}/ws${wsKeyParam}`);
```

---

## FINDING 6: Log Endpoint Leaks Sensitive Information (MEDIUM)

**Issue:** `/api/logs/system` exposes which API keys are configured (boolean), disk usage, and subscriber count. `/api/logs/stream` and `/api/logs/recent` expose full application logs which may contain file paths, API errors with partial key info, and internal system details.

**Fix:** These are now protected by the API key middleware (Finding 1). Additionally, sanitize sensitive data from log output.

In `src/api/routes/logs.py`, update the `WebLogHandler.emit()` method to redact potential secrets:

Find:
```python
            entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
            }
```

Replace with:
```python
            import re
            message = self.format(record)
            # Redact potential API keys and tokens (anything that looks like a key)
            message = re.sub(r'(sk-|gsk_|hf_|pk_)[a-zA-Z0-9]{10,}', r'\1***REDACTED***', message)
            # Redact Bearer tokens
            message = re.sub(r'Bearer [a-zA-Z0-9_\-\.]+', 'Bearer ***REDACTED***', message)
            
            entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
            }
```

---

## FINDING 7: SSE Log Stream Has No Connection Limits (LOW)

**Issue:** The `/api/logs/stream` SSE endpoint has no limit on concurrent subscribers. An attacker (or buggy browser tab) could open hundreds of connections and exhaust server resources.

**Fix:** Add a connection limit.

In `src/api/routes/logs.py`:

Find:
```python
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    log_subscribers.append(queue)
```

Replace with:
```python
    MAX_SUBSCRIBERS = 10
    if len(log_subscribers) >= MAX_SUBSCRIBERS:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many log stream connections"}
        )
    
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    log_subscribers.append(queue)
```

Add the import at the top of logs.py:
```python
from starlette.responses import JSONResponse
```

---

## FINDING 8: Profile ID Not Validated on Creation (LOW)

**Issue:** Profile IDs are used as filenames and directory names. No validation prevents IDs containing shell metacharacters, spaces, or unicode that could cause issues.

**Fix:** Validate profile ID format.

In `src/api/routes/profiles.py`, in `create_profile`, add validation at the start:

Find:
```python
    # 1. Check profile doesn't already exist
    if profile_loader.get_profile(request.id):
```

Add BEFORE it:
```python
    # 0. Validate profile ID format
    import re
    if not re.match(r'^[a-z0-9][a-z0-9_-]{0,63}$', request.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile ID must be lowercase alphanumeric with hyphens/underscores, 1-64 chars, starting with a letter or number"
        )
    
```

---

## FINDING 9: Redis Connection Without Authentication (LOW)

**Issue:** Redis is configured without a password in docker-compose.yml. While it's only accessible within the Docker network (not exposed to the host), it's still best practice to set a password.

**Fix:** Add Redis auth to docker-compose.yml.

In `docker-compose.yml`, update the redis service:

Find:
```yaml
  redis:
    image: redis:7-alpine
    container_name: transcription-redis
    volumes:
      - redis_data:/data
    restart: unless-stopped
```

Replace with:
```yaml
  redis:
    image: redis:7-alpine
    container_name: transcription-redis
    command: redis-server --requirepass ${REDIS_PASSWORD:-changeme}
    volumes:
      - redis_data:/data
    restart: unless-stopped
```

Then update the Redis connections in `src/main.py`:

Find:
```python
            r = aioredis.Redis(host="redis", port=6379)
```

Replace with:
```python
            r = aioredis.Redis(host="redis", port=6379, password=os.getenv("REDIS_PASSWORD", ""))
```

And in `src/worker/processor.py`:

Find:
```python
            self._redis = sync_redis.Redis(host="redis", port=6379, socket_connect_timeout=2)
```

Replace with:
```python
            self._redis = sync_redis.Redis(host="redis", port=6379, password=os.getenv("REDIS_PASSWORD", ""), socket_connect_timeout=2)
```

Add `REDIS_PASSWORD` to your `.env` file.

---

## FINDING 10: Rate Limiting Only on Job Creation (LOW)

**Issue:** Only the `create_job` endpoint has rate limiting (10/minute). Endpoints like dry-run (which makes LLM API calls), profile creation, and file uploads have no rate limits.

**Fix:** Add rate limiting to expensive endpoints.

In `src/api/routes/profiles.py`, add the limiter:

Add imports at the top:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)
```

Then add rate limits to the expensive endpoints:

On `create_profile`:
```python
@router.post("", response_model=ProfileDetailResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_profile(
    request: Request,  # Add this parameter
    profile_request: ProfileCreateRequest,  # Rename from 'request' to avoid conflict
    ...
```

Note: you'll need to rename the `request` parameter to `profile_request` (or similar) throughout the function body since `Request` is now used for rate limiting.

On `dry_run_stage`:
```python
@router.post("/{profile_id}/dry-run")
@limiter.limit("10/minute")
async def dry_run_stage(
    request: Request,
    profile_id: str,
    body: dict,
    ...
```

---

## Summary of Security Posture After Fixes

| Area | Before | After |
|------|--------|-------|
| API Authentication | None | API key on all /api/ routes |
| WebSocket Auth | None | Token via query param |
| File Upload Path Traversal | Vulnerable | Sanitized + resolved path check |
| Prompt File Path Traversal | Vulnerable | Sanitized + resolved path check |
| File Size Limits | Defined but not enforced | Streaming size check with cleanup |
| Log Data Leakage | Full logs exposed unauthenticated | Auth required + key redaction |
| Rate Limiting | Job creation only | Create profile + dry-run + upload |
| Redis Auth | No password | Password required |
| Profile ID Validation | None | Regex format check |
| SSE Connection Limits | Unlimited | Max 10 concurrent |

## Deployment

1. Set `PIPELINE_API_KEY` in your server `.env` file (generate a strong random string)
2. Set `REDIS_PASSWORD` in your server `.env` file
3. Create `frontend/.env` with `VITE_PIPELINE_API_KEY=same-key`
4. Run migration if needed: `python scripts/migrate_add_fields.py data/jobs.db`
5. Rebuild frontend: `cd frontend && npm run build`
6. Rebuild and restart: `docker compose build app worker && docker compose up -d`
