# Caddy Basic Auth for Control Hub

No app code changes needed. Just update your Caddyfile.

---

## Step 1: Generate a password hash

On your VPS, run:

```bash
caddy hash-password --plaintext 'your-chosen-password'
```

This outputs a bcrypt hash like `$2a$14$Zkx19XLiW6...`. Copy it.

If `caddy` isn't in your PATH (e.g. it's running in Docker), use:

```bash
docker run --rm caddy:latest caddy hash-password --plaintext 'your-chosen-password'
```

---

## Step 2: Update your Caddyfile

Your current Caddyfile probably looks something like:

```
transcribe.delboysden.uk {
    reverse_proxy app:8000
}
```

Update it to:

```
transcribe.delboysden.uk {
    basicauth * {
        craig $2a$14$PASTE_YOUR_HASH_HERE
    }
    reverse_proxy app:8000
}
```

Replace `$2a$14$PASTE_YOUR_HASH_HERE` with the actual hash from Step 1.

The `*` means protect all routes — the frontend, the API, WebSocket, everything.

---

## Step 3: Reload Caddy

```bash
# If Caddy is running via Docker:
docker exec caddy caddy reload --config /etc/caddy/Caddyfile

# If Caddy is a systemd service:
sudo systemctl reload caddy
```

---

## Step 4: Update your frontend API key header (optional cleanup)

Since Caddy now handles auth, the browser sends credentials automatically on every request (including API calls and the WebSocket). This means the `PIPELINE_API_KEY` middleware from the security audit is now a second layer rather than the primary one.

You can keep both (defence in depth) or simplify by relying on Caddy auth alone. If keeping both, no changes needed — the browser's basic auth header passes through transparently to FastAPI.

---

## Step 5: Handle WebSocket auth

Browsers automatically send basic auth credentials on WebSocket upgrades when the initial page was authenticated. So the `/ws` endpoint is also protected — no changes needed.

---

## Step 6: SSE log stream

Same as WebSocket — the browser sends credentials on the EventSource connection automatically since the page is already authenticated. Log console works without changes.

---

## Notes

- **Mobile/tablet access**: Basic auth works on all browsers and devices. You'll get a native login prompt.
- **Stream Deck / API scripts**: If you ever call the API from scripts or the Stream Deck, include auth in the request:
  ```bash
  curl -u craig:your-password https://transcribe.delboysden.uk/api/jobs
  ```
- **Logging out**: Basic auth doesn't have a clean logout — closing the browser clears the session. This is the main UX downside but for a single-user tool it's fine.
- **Future upgrade**: If you ever want a nicer login page, you can switch to Cloudflare Access without touching the app. Your DNS is already on CF so it's a 10-minute setup in the Zero Trust dashboard.
