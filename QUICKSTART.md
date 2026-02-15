# Transcription Pipeline - Quick Start

## Running the Full Stack

### 1. Start the API Server
```bash
cd /home/peptifit/transcription-pipeline
.venv/bin/python src/test_api.py
```
API will be available at: http://localhost:8888

### 2. Start the Frontend
```bash
cd /home/peptifit/transcription-pipeline/frontend
npm run dev -- --host
```
Frontend will be available at:
- Local: http://localhost:5173
- Network: http://95.211.44.48:5173

### 3. Start the Worker (Optional)
```bash
cd /home/peptifit/transcription-pipeline
.venv/bin/python src/run_worker.py
```

## Accessing the Application

**Frontend Dashboard**: http://localhost:5173 or http://95.211.44.48:5173
- Upload audio/video files
- Monitor job status
- Download transcription outputs

**API Documentation**: http://localhost:8888/docs
- Interactive API documentation
- Test endpoints directly

## Common Issues

### Frontend not loading
- Make sure to run `npm run dev -- --host` (with `--host` flag)
- Check that port 5173 is not blocked by firewall

### API errors
- Verify environment variables are loaded (`.env` file)
- Check API keys: `GROQ_API_KEY`, `DEEPSEEK_API_KEY`, `HUGGINGFACE_TOKEN`

### Worker not processing jobs
- Ensure worker is running: `.venv/bin/python src/run_worker.py`
- Check database for queued jobs: `sqlite3 transcription.db "SELECT * FROM job;"`
