# Frontend Auth Fix

The frontend API key is empty because Vite bakes `import.meta.env.*` values at build time.
If `frontend/.env` didn't exist when `npm run build` ran, the key is an empty string.

## Fix

### Step 1: Verify the frontend .env file exists with the correct key

```bash
cat frontend/.env
```

It should contain:
```
VITE_PIPELINE_API_KEY=transcription-pipeline-api-key-2025
```

The value MUST exactly match `PIPELINE_API_KEY` in the backend `.env`.

### Step 2: Rebuild the frontend

```bash
cd frontend
npm run build
cd ..
```

### Step 3: Rebuild and restart the app container

```bash
docker compose build app
docker compose up -d
```

### Step 4: Verify

```bash
# This should return 401 (no key):
curl -s -o /dev/null -w "%{http_code}" https://transcribe.delboysden.uk/api/profiles

# This should return 200 (with key):
curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: transcription-pipeline-api-key-2025" https://transcribe.delboysden.uk/api/profiles
```

## Why this happened

Vite replaces `import.meta.env.VITE_PIPELINE_API_KEY` with the literal string value during the build step. If the env var isn't set at that moment, it becomes `""` in the compiled JS bundle. The middleware sees an empty key, rejects the request, and the frontend shows everything as disconnected.
