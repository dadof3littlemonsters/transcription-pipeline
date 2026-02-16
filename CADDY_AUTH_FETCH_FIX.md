# Fix: Frontend Not Sending Basic Auth Credentials

The browser shows a login prompt (Caddy basic auth) and you enter the password. The page HTML loads fine. But all JavaScript `fetch()` calls to `/api/*` fail with 401 because `fetch()` doesn't automatically include the basic auth credentials.

## The Fix

Add `credentials: 'include'` to every `fetch()` call. This tells the browser to send the `Authorization` header that Caddy requires.

### In `frontend/src/ControlHub.jsx`

Find the `apiFetch` function:

```javascript
async function apiFetch(path, options = {}) {
```

Add `credentials: 'include'` to every request. Update the function to:

```javascript
async function apiFetch(path, options = {}) {
  if (API_KEY) {
    options.headers = { ...options.headers, "X-API-Key": API_KEY };
  }
  options.credentials = 'include';
  const res = await fetch(`${API_BASE}${path}`, options);
```

The key line is `options.credentials = 'include';` — add it just before the `fetch()` call.

### In `frontend/src/LogConsole.jsx`

Same fix — find the `apiFetch` function and add `credentials: 'include'`:

```javascript
async function apiFetch(path, options = {}) {
  const apiKey = document.querySelector('meta[name="api-key"]')?.content;
  if (apiKey) {
    options.headers = { ...options.headers, "X-API-Key": apiKey };
  }
  options.credentials = 'include';
  const res = await fetch(`${API_BASE}${path}`, options);
```

### In `frontend/src/api/client.js` (if it exists and is used)

Same pattern — add `credentials: 'include'` to every `fetch()` call in the file.

### WebSocket — no change needed

The browser automatically sends basic auth credentials on WebSocket upgrade requests to the same origin, so the `/ws` connection should work without changes.

### SSE EventSource — needs a workaround

`EventSource` (used by the log console stream) does NOT support sending auth headers. Two options:

**Option A (recommended):** In your Caddyfile, exclude the SSE endpoint from basic auth:

```
transcribe.delboysden.uk {
    @noauth {
        path /api/logs/stream
    }
    route @noauth {
        reverse_proxy app:8000
    }
    
    basicauth * {
        craig $2a$14$YOUR_HASH_HERE
    }
    reverse_proxy app:8000
}
```

This is safe because the SSE endpoint is still protected by the API key middleware in FastAPI.

**Option B:** Replace `EventSource` with `fetch()` in LogConsole.jsx for the SSE stream. This is more complex and less reliable.

## After the fix

```bash
cd frontend && npm run build
cd .. && docker compose build app
docker compose up -d
```

## Why this happens

When you visit `https://transcribe.delboysden.uk` in a browser, Caddy challenges you with basic auth. You enter credentials, the browser caches them, and sends them on all subsequent *navigation* requests (page loads, images, etc.). 

But `fetch()` in JavaScript defaults to `credentials: 'same-origin'` which should work for same-origin requests. However, if the CORS middleware or Caddy is stripping or not forwarding the credentials properly, you need to explicitly set `credentials: 'include'`.
