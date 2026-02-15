# Transcription Pipeline

A complete audio processing pipeline that transcribes audio files, identifies speakers, formats transcripts with AI, and generates professional output documents.

## Features

- 🎙️ **Groq Whisper Transcription**: Fast, accurate transcription using whisper-large-v3-turbo
- 👥 **Speaker Diarization**: Automatic speaker identification with pyannote.audio
- 🤖 **AI Formatting**: DeepSeek-powered formatting for different note types
- 📄 **Multiple Output Formats**: Markdown and Word documents (.docx)
- 📁 **Automatic File Organization**: Organized by note type (meeting, supervision, client, lecture, braindump)
- 🐳 **Dockerized**: Complete containerized setup with Redis queue
- 🔄 **Concurrent Processing**: Handle multiple files simultaneously

## Quick Start

### 1. Prerequisites

- Docker and Docker Compose installed
- API keys for:
  - [Groq](https://console.groq.com/keys) (required for transcription)
  - [DeepSeek](https://platform.deepseek.com/) (optional, for formatting)
  - [HuggingFace](https://huggingface.co/settings/tokens) (optional, for speaker diarization)

### 2. Configuration

Copy the example environment file and add your API keys:

```bash
cp .env.example .env
# Edit .env with your API keys
nano .env
```

Required environment variables:
```bash
GROQ_API_KEY=your_groq_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
HUGGINGFACE_TOKEN=your_huggingface_token_here
```

### 3. Start Services

```bash
docker-compose up -d
```

This starts:
- `transcription-pipeline`: Main API server (port 8888)
- `transcription-worker`: File processing worker
- `transcription-redis`: Job queue

### 4. Verify Setup

```bash
python check_services.py
```

### 5. Process Audio Files

Place audio files in the appropriate upload directory:

```
uploads/
├── meeting/       # Meeting recordings → .md + .docx
├── supervision/   # Clinical supervision → .md + .docx
├── client/        # Client sessions → .md + .docx
├── lecture/       # Lectures → .docx only
└── braindump/     # Voice notes → .md only
```

The worker automatically detects and processes new files:

```
New audio detected → Processing → Transcription → Diarization → 
Formatting → Output generation → Cleanup
```

Outputs are saved to:
- `outputs/transcripts/` - Markdown files
- `outputs/docs/` - Word documents

## Pipeline Flow

```
1. File Detection
   ↓
2. Move to processing/
   ↓
3. Parallel Processing:
   ├─→ Groq Whisper (transcription with timestamps)
   └─→ Pyannote (speaker diarization)
   ↓
4. Merge timestamps with speakers
   ↓
5. DeepSeek formatting (note-type specific)
   ↓
6. Generate outputs:
   ├─→ Markdown (.md) with YAML frontmatter
   └─→ Word document (.docx) via pandoc
   ↓
7. Save to outputs/
   ↓
8. Delete original audio
```

## Note Types

Different formatting is applied based on the upload directory:

| Directory | Output Formats | Formatting Focus |
|-----------|---------------|------------------|
| `meeting/` | .md + .docx | Attendees, decisions, action items |
| `supervision/` | .md + .docx | Supervisor/supervisee, cases, interventions |
| `client/` | .md + .docx | Presenting issues, interventions, risk notes |
| `lecture/` | .docx only | Topic sections, key concepts, summary |
| `braindump/` | .md only | To-dos, ideas, Mermaid mind maps |

## Usage Examples

### Process a Single File

```bash
python test_pipeline.py uploads/meeting/team_sync.mp3 meeting
```

### Run Tests

```bash
# Run inside Docker container
docker exec -e PYTHONPATH=/app/src transcription-pipeline \
    python /app/tests/test_e2e_mock.py
```

### Manual Processing (Python)

```python
from pipeline import process_file_sync

result = process_file_sync("path/to/audio.mp3", "meeting")
print(f"Success: {result['success']}")
print(f"Outputs: {result['outputs']}")
```

### Check Service Health

```bash
# Check all services
python check_services.py

# Check API health
curl http://localhost:8888/health
```

## Configuration Options

Edit `.env` to customize:

```bash
# Paths
UPLOAD_DIR=/home/peptifit/transcription-pipeline/uploads
PROCESSING_DIR=/home/peptifit/transcription-pipeline/processing
OUTPUT_DIR=/home/peptifit/transcription-pipeline/outputs

# Model settings
WHISPER_MODEL=whisper-large-v3-turbo
DIARIZATION_MODEL=pyannote/speaker-diarization-3.1

# Processing
MAX_WORKERS=2
MAX_FILE_SIZE_MB=500

# Output
INCLUDE_TIMESTAMPS=true
INCLUDE_SPEAKER_LABELS=true
```

## API Documentation

The pipeline exposes a FastAPI server at `http://localhost:8888`:

### Endpoints

- `GET /` - Service info
- `GET /health` - Health check
- `GET /ready` - Readiness probe

## Monitoring

View worker logs:

```bash
# All services
docker-compose logs -f

# Just the worker
docker-compose logs -f worker

# API server
docker-compose logs -f app
```

## Troubleshooting

### Worker not processing files

1. Check worker is running: `docker ps | grep worker`
2. Check logs: `docker-compose logs worker`
3. Verify API keys: `python check_services.py`
4. Ensure files are in correct format (.mp3, .wav, .ogg, .m4a, .flac)

### Diarization not working

1. Verify HuggingFace token is set
2. Accept the model license at https://huggingface.co/pyannote/speaker-diarization-3.1
3. Check worker has GPU access (optional but recommended)

### Groq API errors

1. Verify API key is valid: `python check_services.py`
2. Check file size (max 25MB for Groq)
3. Check rate limits in Groq dashboard

### Output files not generated

1. Check `outputs/transcripts/` and `outputs/docs/` exist
2. Verify pandoc is available in container: `docker exec transcription-pipeline which pandoc`
3. Check DeepSeek API key if formatting fails

## File Structure

```
transcription-pipeline/
├── src/
│   ├── config.py          # Configuration management
│   ├── transcription.py   # Groq Whisper client
│   ├── diarization.py     # Pyannote speaker diarization
│   ├── merge.py           # Timestamp merging logic
│   ├── formatting.py      # DeepSeek formatting
│   ├── output.py          # Output generation (.md, .docx)
│   ├── pipeline.py        # Main orchestrator
│   ├── file_watcher.py    # File monitoring
│   ├── worker.py          # Background worker
│   └── main.py            # API server
├── tests/
│   ├── test_pipeline_components.py
│   └── test_e2e_mock.py
├── uploads/               # Input directory (mounted)
├── processing/            # Processing directory (mounted)
├── outputs/               # Output directory (mounted)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── check_services.py      # Health check script
└── test_pipeline.py       # CLI test script
```

## Development

### Run Tests

```bash
# Component tests
docker exec -e PYTHONPATH=/app/src transcription-pipeline \
    python -m pytest tests/ -v

# Mock end-to-end test
docker exec -e PYTHONPATH=/app/src transcription-pipeline \
    python /app/tests/test_e2e_mock.py
```

### Rebuild Containers

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Add New Note Type

1. Add prompt template in `src/formatting.py`
2. Add to `PROMPT_TEMPLATES` dictionary
3. Update note type detection in `src/worker.py`
4. Update output rules in `src/output.py`

## License

MIT

## Support

For issues and feature requests, please open a GitHub issue.
