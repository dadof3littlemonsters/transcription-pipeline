# Transcription Pipeline & Control Hub — Architecture v2

## 1. Project Vision

A self-hosted, modular transcription system that ingests audio (lectures, meetings, interviews), processes it through configurable AI pipelines, and delivers polished documents to your devices. The **Control Hub** provides a web dashboard for managing profiles, uploading files, monitoring jobs, and configuring the system — no CLI required.

Key design goals:

- **Modular profiles** — add a new use case (work meeting notes, data protection lecture) by dropping in a YAML file
- **WAF-friendly** — your wife uploads a lecture recording and gets formatted notes on her device without touching a terminal
- **Cost-aware** — route cheap tasks to cheap models, expensive analysis to capable models
- **Vibe-codeable** — React frontend, Python backend, clear API contracts between them

---

## 2. Container Ecosystem

| Service | Container | Role | Port (internal) |
|---|---|---|---|
| **Pipeline API** | `transcription-api` | FastAPI backend. REST API for Control Hub, job management, profile CRUD. | 8000 |
| **Control Hub** | `transcription-hub` | React SPA (Nginx). The web dashboard. | 3000 |
| **Worker** | `transcription-worker` | Background processor. Pulls jobs from Redis, runs AI stages. | — |
| **Redis** | `transcription-redis` | Job queue (Bull/BullMQ-style via Python RQ or arq), pub/sub for real-time updates. | 6379 |
| **SQLite** | *(volume mount)* | Persistent job history, profile metadata, audit log. No extra container needed. | — |
| **Caddy** | `peptifit_caddy` | Reverse proxy, SSL termination, domain routing. | 80/443 |
| **Syncthing** | `peptifit_syncthing` | File sync — pushes completed documents to family devices. | 8384 |

All containers share the `peptifit_stack` bridge network for internal DNS resolution.

---

## 3. Infrastructure & Networking

### 3.1 Domain Routing (Caddy)

```caddyfile
transcribe.delboysden.uk {
    # API requests
    handle /api/* {
        reverse_proxy transcription-api:8000
    }

    # WebSocket for real-time job updates
    handle /ws/* {
        reverse_proxy transcription-api:8000
    }

    # Control Hub SPA (everything else)
    handle {
        reverse_proxy transcription-hub:3000
    }
}
```

### 3.2 File Synchronization (Syncthing)

- **Shared volume**: `outputs/` mounted into both `transcription-worker` and `peptifit_syncthing`
- **Sync targets**: Family devices connected via Syncthing
- **Monitoring**: Control Hub queries Syncthing REST API:
  - `/rest/system/status` — system health
  - `/rest/db/completion?folder=<id>` — per-folder sync progress (e.g. "3 files pending")
  - `/rest/system/connections` — connected device count

### 3.3 Tailscale Integration

If accessing from outside the home network, Caddy can bind to the Tailscale interface or you can access services directly via Tailscale IPs. No additional config needed since your VPS and home lab are already on the tailnet.

---

## 4. Tech Stack Recommendations

### 4.1 Backend — FastAPI (Python)

**Why**: You're already using it, Whisper/Pyannote are Python-native, and FastAPI gives you automatic OpenAPI docs for every endpoint (helpful when vibe-coding the frontend).

Key libraries:

- **arq** — async Redis job queue (lighter than Celery, Python-native, good for this scale)
- **SQLModel** — SQLite ORM by the FastAPI creator (simpler than Prisma for Python, same SQLite comfort)
- **watchfiles** — async file watcher for hot-reloading profiles
- **pyyaml** — profile/prompt config parsing
- **websockets** — real-time job progress to the Control Hub

### 4.2 Frontend — React + Vite + Tailwind

**Why**: Matches your experience. Vite for fast dev iteration. Tailwind for rapid styling without faffing with CSS files.

Key libraries:

- **React Query (TanStack Query)** — server state management, auto-refetching, caching
- **react-dropzone** — drag-and-drop file uploads
- **Lucide React** — clean icon set
- **Recharts** — if you want job/cost analytics charts later
- **Headless UI** — accessible dropdowns, modals, toggles (pairs with Tailwind)

Build output gets served by Nginx in the `transcription-hub` container, or you can simplify and have FastAPI serve the built static files (one fewer container).

### 4.3 AI Services

| Task | Service | Model | Notes |
|---|---|---|---|
| Transcription | Groq API | Whisper Large v3 | Fast, cheap, accurate |
| Speaker diarization | Local | Pyannote 3.1 | Runs in worker container, needs ~2GB RAM |
| Cleaning (Stage 1) | DeepSeek / local | DeepSeek Chat or Qwen 2.5 | Cheap model for mechanical cleanup |
| Analysis (Stage 2+) | DeepSeek API | DeepSeek Chat | Heavier reasoning, worth the cost |
| Fallback/routing | OpenRouter | Any | Cost-based model routing if primary is down |

---

## 5. Profile System (The Core Modularity)

### 5.1 Profile Schema

Each profile is a self-contained YAML file in `config/profiles/`:

```yaml
# config/profiles/business_lecture.yaml
id: business_lecture
name: "Keira"
description: "Business & Management lectures"
icon: "briefcase"  # Lucide icon name for the Control Hub UI
active: true

input:
  watch_folder: "uploads/business_lecture"
  accepted_formats: [".mp3", ".m4a", ".wav", ".ogg", ".webm"]
  max_file_size_mb: 500

transcription:
  provider: "groq"
  model: "whisper-large-v3"
  language: "en"
  mode: "clean_verbatim"  # or "verbatim", "summary"

diarization:
  enabled: true
  min_speakers: 1
  max_speakers: 4

stages:
  - id: "clean"
    name: "Clean & Structure"
    model: "deepseek-chat"
    provider: "deepseek"
    prompt_file: "prompts/business/stage_1_clean.md"
    output_format: "md"
    
  - id: "analyse"
    name: "Strategic Analysis"
    model: "deepseek-chat"
    provider: "deepseek"
    prompt_file: "prompts/business/stage_2_analysis.md"
    output_format: "md"
    input_from: "clean"  # chains from previous stage
    
  - id: "cheatsheet"
    name: "Cheat Sheet"
    model: "deepseek-chat"
    provider: "deepseek"
    prompt_file: "prompts/business/stage_3_cheatsheet.md"
    output_format: "md"
    input_from: "analyse"

output:
  folder: "outputs/docs/keira"
  formats: ["md", "docx"]  # auto-convert md to docx via pandoc
  naming: "{date}_{original_filename}_{stage}"

notifications:
  on_complete: true  # future: push notification, email, Discord webhook
```

### 5.2 Adding a New Profile

To add your own work profile, you just:

1. Create `config/profiles/my_work_meeting.yaml`
2. Create prompt files in `config/prompts/work/`
3. The worker detects the new profile on next poll (or trigger reload from Control Hub)

No code changes. No container restart.

### 5.3 Prompt Files

Prompts live as standalone Markdown files for easy editing:

```markdown
<!-- config/prompts/business/stage_1_clean.md -->
# System Prompt: Business Lecture Cleanup

You are a professional transcription editor. Clean the following lecture transcript:

## Rules
- Fix grammar and filler words (um, uh, like)
- Preserve technical terminology exactly
- Break into logical sections with headers
- Maintain speaker attributions if present

## Output Format
Structured Markdown with headers, paragraphs, and key terms in **bold**.
```

---

## 6. API Design

### 6.1 Core Endpoints

```
# Profiles
GET    /api/profiles                    — List all profiles
GET    /api/profiles/{id}               — Get profile detail + stats
PUT    /api/profiles/{id}               — Update profile config
POST   /api/profiles/{id}/reload        — Hot-reload this profile's config

# Jobs
POST   /api/profiles/{id}/upload        — Upload file to profile
GET    /api/jobs                         — List jobs (filterable by profile, status)
GET    /api/jobs/{id}                    — Job detail (stages, progress, outputs)
POST   /api/jobs/{id}/retry              — Retry failed job
POST   /api/jobs/{id}/retry-stage/{n}    — Re-run specific stage only
DELETE /api/jobs/{id}                    — Cancel/remove job

# System
GET    /api/health                       — Service health (Redis, Whisper, DeepSeek, Syncthing)
GET    /api/health/syncthing             — Detailed sync status per folder
GET    /api/stats                        — Dashboard stats (jobs today, cost estimate, avg time)
WS     /ws/jobs                          — Real-time job progress stream
```

### 6.2 Job Lifecycle

```
QUEUED → TRANSCRIBING → DIARIZING → STAGE_1 → STAGE_2 → ... → CONVERTING → SYNCING → COMPLETE
                                                                                  ↓
                                                                               FAILED
```

Each stage transition is broadcast over WebSocket so the Control Hub updates live.

---

## 7. Control Hub — UI Layout

### 7.1 Dashboard (Home)

```
┌─────────────────────────────────────────────────────────────┐
│  🏠 Control Hub                            ● Syncthing: OK  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ 💼 Keira │  │ 📚 Kate  │  │ 🔧 Craig │  │  + New   │   │
│  │ Business │  │ SocWork  │  │  Work    │  │ Profile  │   │
│  │ 3 done   │  │ 1 active │  │ 0 jobs   │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                             │
│  Recent Activity                                            │
│  ─────────────                                              │
│  ✅ Lecture_Week8.mp3      Keira    Complete    2m ago       │
│  🔄 SWK_Seminar_3.m4a     Kate     Stage 2     just now     │
│  ❌ Meeting_Feb10.wav      Craig    Failed      1h ago       │
│                                                             │
│  System Health                                              │
│  ─────────────                                              │
│  Groq Whisper: ●  DeepSeek: ●  Redis: ●  Syncthing: ●     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Profile View

- Upload zone (drag-and-drop)
- Active/completed jobs for this profile
- Edit prompts (in-browser Markdown editor with preview)
- Pipeline visualisation (stage flow diagram)
- Toggle profile active/inactive

### 7.3 Job Detail View

- Stage-by-stage progress with timestamps and duration
- Expandable output preview for each stage
- "Re-run from Stage X" button
- Download individual stage outputs or final bundle
- Cost breakdown per stage (token usage × model price)

---

## 8. Data Model (SQLite via SQLModel)

```python
class Job(SQLModel, table=True):
    id: str                    # UUID
    profile_id: str            # links to YAML profile
    filename: str              # original upload filename
    status: str                # QUEUED, TRANSCRIBING, STAGE_1, ..., COMPLETE, FAILED
    current_stage: str | None  # which stage is active
    created_at: datetime
    completed_at: datetime | None
    error: str | None
    cost_estimate: float       # accumulated token cost in USD

class StageResult(SQLModel, table=True):
    id: str                    # UUID
    job_id: str                # FK to Job
    stage_id: str              # e.g. "clean", "analyse", "cheatsheet"
    status: str                # PENDING, RUNNING, COMPLETE, FAILED
    started_at: datetime | None
    completed_at: datetime | None
    input_tokens: int
    output_tokens: int
    model_used: str
    output_path: str | None    # path to stage output file
    error: str | None
```

This gives you full audit trail — you can see exactly which model processed each stage, how many tokens it used, and re-run any individual stage.

---

## 9. Worker Architecture

```
┌─────────────────────────────────────────────┐
│              transcription-worker            │
│                                              │
│  ┌──────────┐    ┌───────────────────────┐  │
│  │  Profile  │    │     Job Processor     │  │
│  │  Watcher  │    │                       │  │
│  │           │    │  1. Transcribe (Groq) │  │
│  │ Watches:  │    │  2. Diarize (Pyannote)│  │
│  │ config/   │    │  3. Run stages[]      │  │
│  │ profiles/ │    │  4. Convert formats   │  │
│  └──────────┘    │  5. Write to outputs/  │  │
│                   └───────────────────────┘  │
│                            ↕                 │
│                   ┌───────────────┐          │
│                   │  Redis Queue  │          │
│                   └───────────────┘          │
│                            ↕                 │
│                   ┌───────────────┐          │
│                   │    SQLite     │          │
│                   │  (job history)│          │
│                   └───────────────┘          │
└─────────────────────────────────────────────┘
```

### 9.1 Stage Caching

Each stage writes its output to a known path:

```
processing/{job_id}/transcript.md
processing/{job_id}/diarized.md
processing/{job_id}/stage_clean.md
processing/{job_id}/stage_analyse.md
processing/{job_id}/stage_cheatsheet.md
```

This means if you tweak the cheat sheet prompt, you can re-run just that stage — it reads from the cached `stage_analyse.md` output rather than reprocessing the entire file.

### 9.2 Error Handling & Retries

- Each stage is independently retryable
- Failed jobs are marked with the failing stage and error message
- Automatic retry with exponential backoff for transient API errors (rate limits, timeouts)
- Dead letter queue for jobs that fail 3 times — visible in Control Hub for manual review

---

## 10. Cost Management

### 10.1 Per-Job Cost Tracking

The worker logs token counts for every AI call. With known pricing per model:

```python
PRICING = {
    "whisper-large-v3": {"per_minute": 0.006},     # Groq
    "deepseek-chat":    {"input_1m": 0.14, "output_1m": 0.28},
    "qwen-2.5-72b":    {"input_1m": 0.10, "output_1m": 0.20},
}
```

The Control Hub can show: cost per job, cost per profile (monthly), and cost per stage — so you can spot if one stage is burning tokens and should use a cheaper model.

### 10.2 Model Routing per Stage

The profile schema lets you assign different models per stage:

```yaml
stages:
  - id: "clean"
    model: "qwen-2.5-72b"      # cheap model for mechanical cleanup
    provider: "openrouter"
  - id: "analyse"
    model: "deepseek-chat"      # capable model for reasoning
    provider: "deepseek"
```

---

## 11. Directory Structure

```
/home/peptifit/transcription-pipeline/
├── config/
│   ├── profiles/
│   │   ├── business_lecture.yaml      # Keira
│   │   ├── social_work.yaml           # Kate
│   │   └── work_meetings.yaml         # Craig (your own)
│   ├── prompts/
│   │   ├── business/
│   │   │   ├── stage_1_clean.md
│   │   │   ├── stage_2_analysis.md
│   │   │   └── stage_3_cheatsheet.md
│   │   ├── social_work/
│   │   │   └── ...
│   │   └── work/
│   │       └── ...
│   └── models.yaml                    # AI provider config & API keys reference
├── src/
│   ├── api/
│   │   ├── main.py                    # FastAPI app entry
│   │   ├── routes/
│   │   │   ├── profiles.py
│   │   │   ├── jobs.py
│   │   │   ├── health.py
│   │   │   └── websocket.py
│   │   └── models.py                  # SQLModel definitions
│   ├── worker/
│   │   ├── processor.py               # Job execution engine
│   │   ├── transcriber.py             # Groq Whisper client
│   │   ├── diarizer.py                # Pyannote wrapper
│   │   ├── formatter.py               # LLM stage runner
│   │   ├── converter.py               # md → docx conversion
│   │   └── profile_loader.py          # YAML parser + hot-reload
│   └── shared/
│       ├── config.py                  # Environment / settings
│       ├── database.py                # SQLite connection
│       └── redis_client.py
├── hub/                               # React app (Vite)
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── ProfileCard.jsx
│   │   │   ├── JobList.jsx
│   │   │   ├── UploadZone.jsx
│   │   │   ├── StageProgress.jsx
│   │   │   ├── PromptEditor.jsx
│   │   │   └── HealthIndicator.jsx
│   │   ├── hooks/
│   │   │   ├── useJobs.js             # React Query hook
│   │   │   └── useWebSocket.js        # Live updates
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── uploads/                           # Per-profile watch folders
│   ├── business_lecture/
│   ├── social_work/
│   └── work_meetings/
├── processing/                        # Temp working directory per job
├── outputs/
│   └── docs/
│       ├── keira/
│       ├── kate/
│       └── craig/
├── data/
│   └── pipeline.db                    # SQLite database
├── docker-compose.yml
├── Dockerfile.api
├── Dockerfile.worker
└── Dockerfile.hub
```

---

## 12. Docker Compose

```yaml
version: "3.8"

services:
  transcription-api:
    build:
      context: .
      dockerfile: Dockerfile.api
    container_name: transcription-api
    volumes:
      - ./config:/app/config
      - ./uploads:/app/uploads
      - ./outputs:/app/outputs
      - ./processing:/app/processing
      - ./data:/app/data
    environment:
      - REDIS_URL=redis://transcription-redis:6379
      - DATABASE_URL=sqlite:///app/data/pipeline.db
      - GROQ_API_KEY=${GROQ_API_KEY}
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - SYNCTHING_API_KEY=${SYNCTHING_API_KEY}
      - SYNCTHING_URL=http://syncthing:8384
    networks:
      - peptifit_stack
    restart: unless-stopped

  transcription-worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    container_name: transcription-worker
    volumes:
      - ./config:/app/config
      - ./uploads:/app/uploads
      - ./outputs:/app/outputs
      - ./processing:/app/processing
      - ./data:/app/data
    environment:
      - REDIS_URL=redis://transcription-redis:6379
      - DATABASE_URL=sqlite:///app/data/pipeline.db
      - GROQ_API_KEY=${GROQ_API_KEY}
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
    networks:
      - peptifit_stack
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 4G  # Pyannote needs ~2GB

  transcription-hub:
    build:
      context: ./hub
      dockerfile: Dockerfile.hub
    container_name: transcription-hub
    networks:
      - peptifit_stack
    restart: unless-stopped

  transcription-redis:
    image: redis:7-alpine
    container_name: transcription-redis
    volumes:
      - redis_data:/data
    networks:
      - peptifit_stack
    restart: unless-stopped

networks:
  peptifit_stack:
    external: true

volumes:
  redis_data:
```

---

## 13. Implementation Roadmap

### Phase 1 — Foundation (Current → Next)
- [ ] Refactor existing pipeline code into `src/worker/` module structure
- [ ] Implement profile YAML schema and loader with validation
- [ ] Set up SQLite database with SQLModel
- [ ] Migrate existing prompts to Markdown files in `config/prompts/`
- [ ] Add stage caching (write intermediate outputs to `processing/`)

### Phase 2 — API Layer
- [ ] FastAPI routes for profiles, jobs, health
- [ ] Redis job queue integration (arq)
- [ ] WebSocket endpoint for live job updates
- [ ] Syncthing API integration for sync status
- [ ] Stage-level retry endpoint

### Phase 3 — Control Hub Frontend
- [ ] Vite + React + Tailwind project scaffold
- [ ] Dashboard with profile cards and recent activity
- [ ] File upload with drag-and-drop per profile
- [ ] Real-time job progress via WebSocket
- [ ] Health status indicators

### Phase 4 — Polish & Extend
- [ ] In-browser prompt editor with Markdown preview
- [ ] Cost tracking dashboard (per job, per profile, monthly)
- [ ] Add your work profiles
- [ ] Notification system (Discord webhook on completion)
- [ ] Caddy config + SSL for `transcribe.delboysden.uk`
- [ ] Mobile-friendly responsive layout (WAF factor)

---

## 14. Quick Reference — Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Job queue | arq (Python) | Async, lightweight, Redis-backed, fits the Python ecosystem |
| Database | SQLite via SQLModel | No extra container, sufficient for this scale, familiar territory |
| Frontend framework | React + Vite | Matches your experience, fast iteration for vibe coding |
| Styling | Tailwind CSS | Rapid prototyping, no separate CSS files to manage |
| Profile config | YAML files | Human-readable, git-trackable, hot-reloadable |
| Prompt storage | Standalone .md files | Easy to edit, version, and preview |
| Real-time updates | WebSocket | Simpler than SSE for bidirectional potential, good React Query integration |
| File sync | Syncthing (existing) | Already in your stack, works well for family devices |
| Reverse proxy | Caddy (existing) | Already in your stack, automatic HTTPS |
