# Transcription Pipeline - Usage Guide

## Quick Start

```bash
cd /home/peptifit/transcription-pipeline

# Interactive setup
./quickstart.sh

# Or run setup directly
./quickstart.sh setup
```

## Step-by-Step Setup

### 1. Configure API Keys

Edit `.env` and add your API keys:

```bash
# Required
GROQ_API_KEY=groq_api_key_here

# Optional but recommended
DEEPSEEK_API_KEY=deepseek_api_key_here
HUGGINGFACE_TOKEN=huggingface_token_here
```

Get your keys:
- **Groq**: https://console.groq.com/keys (required for transcription)
- **DeepSeek**: https://platform.deepseek.com/ (for AI formatting)
- **HuggingFace**: https://huggingface.co/settings/tokens (for speaker diarization)

### 2. Start Services

```bash
docker-compose up -d
```

Wait for services to start:
```bash
docker-compose ps
```

### 3. Verify Setup

```bash
# Check all services
python check_services.py

# Or use curl
curl http://localhost:8888/health
```

### 4. Process Audio Files

Place files in the appropriate upload directory:

```bash
# Meeting recording
cp meeting.mp3 uploads/meeting/

# Clinical supervision
cp supervision.wav uploads/supervision/

# Voice note
cp ideas.ogg uploads/braindump/
```

The worker automatically processes new files.

### 5. Monitor Processing

```bash
# Watch worker logs
docker-compose logs -f worker

# Check outputs
ls -la outputs/transcripts/
ls -la outputs/docs/
```

## Output Formats by Type

| Note Type | Directory | Markdown | Word Doc | Description |
|-----------|-----------|----------|----------|-------------|
| Meeting | `uploads/meeting/` | ✓ | ✓ | Attendees, decisions, action items |
| Supervision | `uploads/supervision/` | ✓ | ✓ | Cases, interventions, goals |
| Client | `uploads/client/` | ✓ | ✓ | Session notes, risk assessment |
| Lecture | `uploads/lecture/` | - | ✓ | Key concepts, summary |
| Braindump | `uploads/braindump/` | ✓ | - | To-dos, mind map |

## Sample Outputs

### Markdown Output

```markdown
---
title: "Meeting: Team Sync 2024"
date: 2024-02-04
type: meeting
duration: 1800
speakers: SPEAKER_00, SPEAKER_01
---

# Meeting Notes

## Attendees
- Project Manager (SPEAKER_00)
- Developer (SPEAKER_01)

## Discussion Summary
- Reviewed Q4 roadmap
- Discussed resource allocation

## Action Items
1. Create project timeline (PM)
2. Review API documentation (Dev)
```

### Word Document

- Professional formatting with title page
- Speaker labels in bold
- Proper headings and lists
- Metadata in header/footer

## Testing

### Run All Tests

```bash
./quickstart.sh test
```

### Test Single File

```bash
python test_pipeline.py uploads/meeting/test.mp3 meeting
```

### Mock End-to-End Test

```bash
docker exec -e PYTHONPATH=/app/src transcription-pipeline \
    python /app/tests/test_e2e_mock.py
```

## Troubleshooting

### Services won't start

```bash
# Check Docker is running
docker info

# Rebuild containers
docker-compose down
docker-compose up -d --build

# Check logs
docker-compose logs
```

### Files not processing

1. Check worker is running:
   ```bash
   docker-compose ps
   ```

2. Check logs for errors:
   ```bash
   docker-compose logs worker
   ```

3. Verify API keys:
   ```bash
   python check_services.py
   ```

4. Check file format:
   ```bash
   file uploads/meeting/your_file.mp3
   ```

### Diarization not working

1. Verify HuggingFace token is set
2. Accept the model license:
   https://huggingface.co/pyannote/speaker-diarization-3.1
3. Check token has "read" access

### Groq API errors

1. Verify API key is valid
2. Check file size < 25MB
3. Check Groq dashboard for rate limits

### Output files missing

1. Check `outputs/` directory exists and is writable
2. Verify DeepSeek API key (for formatting)
3. Check pandoc is installed in container:
   ```bash
   docker exec transcription-pipeline which pandoc
   ```

## Common Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart worker
docker-compose restart worker

# View logs
docker-compose logs -f worker
docker-compose logs -f app

# Shell into container
docker exec -it transcription-pipeline bash

# Check disk space
df -h

# Clean up old outputs
find outputs/ -name "*.md" -mtime +30 -delete
```

## Configuration

Edit `.env` to customize:

```bash
# Processing
MAX_FILE_SIZE_MB=500          # Max upload size
MAX_WORKERS=2                 # Parallel processing

# Output
INCLUDE_TIMESTAMPS=true       # Add timestamps
INCLUDE_SPEAKER_LABELS=true   # Add speaker labels

# Models
WHISPER_MODEL=whisper-large-v3-turbo
DIARIZATION_MODEL=pyannote/speaker-diarization-3.1
```

## Directory Structure

```
transcription-pipeline/
├── uploads/          # Drop audio files here
│   ├── meeting/
│   ├── supervision/
│   ├── client/
│   ├── lecture/
│   └── braindump/
├── processing/       # Files being processed
│   └── errors/       # Failed files
├── outputs/          # Generated files
│   ├── transcripts/  # Markdown files
│   └── docs/         # Word documents
└── logs/             # Application logs
```

## API Endpoints

The API server runs on port 8888:

```bash
# Health check
curl http://localhost:8888/health

# Service info
curl http://localhost:8888/
```

## Support

For issues:
1. Check logs: `docker-compose logs`
2. Run health check: `python check_services.py`
3. Run tests: `./quickstart.sh test`
