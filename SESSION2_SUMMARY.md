# Session 2: Core Processing Pipeline - Complete ✅

## Overview
The complete audio processing pipeline has been built and is ready for testing with API keys.

## ✅ Components Built

### 1. Groq Whisper Integration (`src/transcription.py`)
- **Class**: `GroqTranscriber`
- **Model**: whisper-large-v3-turbo
- **Features**:
  - Segment-level timestamps
  - Language detection
  - Retry logic for rate limits (429) and server errors (5xx)
  - Audio validation (size < 25MB, supported formats)
  - Rich logging with progress indicators

### 2. Pyannote Speaker Diarization (`src/diarization.py`)
- **Class**: `SpeakerDiarizer`
- **Model**: pyannote/speaker-diarization-3.1
- **Features**:
  - Lazy model loading
  - Automatic device detection (CUDA/CPU)
  - Returns speaker timeline (SPEAKER_00, SPEAKER_01, etc.)
  - Single-speaker fallback

### 3. Timestamp Merge Logic (`src/merge.py`)
- **Function**: `merge_transcript_with_speakers()`
- **Algorithm**:
  - Calculates overlap between Whisper segments and speaker segments
  - Assigns speaker with highest overlap (>50% threshold)
  - Merges consecutive segments from same speaker
  - Handles edge cases (empty diarization, unknown speakers)

### 4. DeepSeek Formatting (`src/formatting.py`)
- **Class**: `DeepSeekFormatter`
- **Model**: deepseek-chat
- **Note-Type Prompts**:
  | Type | Sections |
  |------|----------|
  | meeting | Attendees, Discussion, Decisions, Action Items |
  | supervision | Participants, Cases, Interventions, Learning Points |
  | client | Session Type, Issues, Interventions, Risk Assessment |
  | lecture | Title, Sections, Key Concepts, Summary |
  | braindump | To-Do, Ideas, Mind Map (Mermaid), Categories |

### 5. Output Generation (`src/output.py`)
- **Class**: `OutputGenerator`
- **Formats**:
  | Note Type | Markdown | Word Doc |
  |-----------|----------|----------|
  | meeting | ✓ | ✓ |
  | supervision | ✓ | ✓ |
  | client | ✓ | ✓ |
  | lecture | - | ✓ |
  | braindump | ✓ | - |
- **Features**:
  - YAML frontmatter in markdown
  - Word headings from markdown headers
  - Bullet/numbered list conversion
  - Title page with metadata

### 6. Pipeline Orchestrator (`src/pipeline.py`)
- **Class**: `TranscriptionPipeline`
- **Flow**:
  ```
  1. Groq Whisper transcription
  2. Pyannote speaker diarization (parallel)
  3. Timestamp merging
  4. DeepSeek formatting
  5. Output generation (md + docx)
  6. Cleanup (delete original audio)
  ```
- **Error Handling**:
  - Retry logic for API failures
  - Failed files moved to `processing/errors/`
  - Graceful degradation (e.g., skip formatting if DeepSeek fails)

### 7. Worker Integration (`src/worker.py`)
- **Class**: `PipelineWorker`
- **Features**:
  - Health checks on startup
  - Note type detection from directory name
  - Automatic processing of uploaded files
  - Rich console logging

## 📁 Project Structure

```
/home/peptifit/transcription-pipeline/
├── src/
│   ├── __init__.py
│   ├── config.py              # Configuration management
│   ├── file_watcher.py        # File monitoring
│   ├── worker.py              # Worker with pipeline integration
│   ├── pipeline.py            # Main orchestrator
│   ├── transcription.py       # Groq Whisper client
│   ├── diarization.py         # Pyannote diarization
│   ├── merge.py               # Timestamp merging
│   ├── formatting.py          # DeepSeek formatter
│   └── output.py              # Output generation
├── uploads/                   # Upload directories by type
│   ├── meeting/
│   ├── supervision/
│   ├── client/
│   ├── lecture/
│   └── braindump/
├── processing/                # Files being processed
│   └── errors/                # Failed files
├── outputs/
│   ├── transcripts/           # Markdown files
│   └── docs/                  # Word documents
├── logs/                      # Application logs
├── models/                    # ML models (cached)
├── docker-compose.yml         # Container orchestration
├── Dockerfile                 # Container definition
├── requirements.txt           # Python dependencies
├── .env.example              # Environment template
├── test_pipeline.py          # Test script
└── PROJECT_SUMMARY.md        # Previous session summary
```

## 🚀 Current Status

### Running Containers
```
transcription-pipeline    Up (healthy)   Port 8888 (API)
transcription-worker      Up (healthy)   Pipeline worker
transcription-redis       Up (healthy)   Redis cache
```

### Health Check (Current)
```
Groq API:       ✗ (needs API key)
Diarization:    ✓ (ready)
DeepSeek API:   ✗ (needs API key)
```

## 🔑 Required API Keys

Add these to `/home/peptifit/transcription-pipeline/.env`:

```bash
# Required for transcription
GROQ_API_KEY=your_groq_key_here

# Required for formatting
DEEPSEEK_API_KEY=your_deepseek_key_here

# Required for speaker diarization
HUGGINGFACE_TOKEN=your_hf_token_here
```

### How to Get Keys

1. **Groq API Key**: https://console.groq.com/keys
   - Free tier: 1M tokens/day
   - Models: whisper-large-v3-turbo

2. **DeepSeek API Key**: https://platform.deepseek.com/
   - Models: deepseek-chat
   - Good for long context formatting

3. **HuggingFace Token**: https://huggingface.co/settings/tokens
   - Required for pyannote models
   - Also accept user agreement at: https://huggingface.co/pyannote/speaker-diarization-3.1

## 🧪 Testing

### Component Tests

Run comprehensive tests inside the Docker container:

```bash
# Run mock end-to-end tests (no API keys required)
docker exec -e PYTHONPATH=/app/src transcription-pipeline \
    python /app/tests/test_e2e_mock.py
```

Expected output:
```
============================================================
TEST SUMMARY
============================================================
  Merge Logic: ✓ PASSED
  Output Generation: ✓ PASSED
  Formatting Prompts: ✓ PASSED
  Full Pipeline: ✓ PASSED
  Note Type Detection: ✓ PASSED
  Error Handling: ✓ PASSED

Total: 6 tests, 6 passed, 0 failed
```

### Test with a Sample File

1. Copy an audio file to an upload directory:
```bash
cp /path/to/audio.ogg /home/peptifit/transcription-pipeline/uploads/meeting/
```

2. The worker will automatically detect and process it.

3. Watch logs:
```bash
docker-compose logs -f worker
```

### Manual Test (with API keys set)

```bash
cd /home/peptifit/transcription-pipeline
python test_pipeline.py uploads/meeting/test.mp3 meeting
```

### Health Check

```bash
# Check all services
python check_services.py

# Check specific component
curl http://localhost:8888/health
```

## 📊 Expected Output

For a meeting audio file, you'll get:

### Markdown Output (`outputs/transcripts/`)
```yaml
---
title: "Meeting - Test Discussion"
date: "2026-02-04T16:55:00"
type: meeting
duration: 1800
speakers: 3
---

**SPEAKER_00:**
Welcome everyone to today's meeting...

**SPEAKER_01:**
Thanks for having me. I wanted to discuss...
```

### Word Document (`outputs/docs/`)
- Formatted with proper headings
- Speaker labels as bold text
- Bullet points preserved
- Title page with metadata

## 🔧 Commands

```bash
# Start all services
cd /home/peptifit/transcription-pipeline
docker-compose up -d

# View worker logs
docker-compose logs -f worker

# Restart after code changes
docker-compose down
docker build -t transcription-pipeline:latest .
docker-compose up -d

# Stop services
docker-compose down

# Check health
docker exec transcription-worker python -c "from pipeline import TranscriptionPipeline; p = TranscriptionPipeline(); print(p.health_check())"

# Process single file manually
docker exec transcription-worker python src/pipeline.py /app/processing/audio.mp3 meeting
```

## 📝 Next Steps (Session 3)

### Email Notifications
- SMTP configuration
- Send completion emails with download links
- Include summary of transcription

### Web Download Portal
- FastAPI endpoints for file listing/download
- Secure token-based access
- File expiration handling

### Obsidian Sync
- Webhook/API integration
- Automatic vault updates
- Tag/category assignment based on note type

### Advanced Features
- Concurrent processing with Redis queue
- Webhook callbacks for mobile apps
- Prometheus metrics and Grafana dashboards

## ⚠️ Known Limitations

1. **No GPU**: Running on CPU (CUDA not available in container)
   - Pyannote diarization will be slower
   - Consider GPU-enabled container for production

2. **No Queue**: Currently processes files sequentially
   - Redis is running but not used for queueing yet
   - Multiple worker replicas will conflict

3. **No Persistence**: Failed files moved to errors/ but not retried
   - Manual intervention required
   - Retry logic planned for Session 3

## ✅ Checklist

- [x] Groq Whisper API integration
- [x] Pyannote speaker diarization
- [x] Timestamp merging logic
- [x] DeepSeek formatting with prompts
- [x] Markdown output generation
- [x] Word document generation
- [x] File cleanup after processing
- [x] Error handling and retry logic
- [x] Worker integration with file watcher
- [x] Docker setup with pandoc
- [ ] Test with real API keys (pending user input)
- [ ] Email notifications (Session 3)
- [ ] Web portal (Session 3)
- [ ] Obsidian sync (Session 3)

---

**Ready for testing once API keys are provided!** 🚀
