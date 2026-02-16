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
from starlette.responses import JSONResponse

router = APIRouter(prefix="/api/logs", tags=["Logs"])

LOG_BUFFER_SIZE = 500
log_buffer: deque = deque(maxlen=LOG_BUFFER_SIZE)
log_subscribers: list[asyncio.Queue] = []


class WebLogHandler(logging.Handler):
    """Custom logging handler that captures logs for the web console."""
    
    def emit(self, record):
        try:
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
    
    MAX_SUBSCRIBERS = 10
    if len(log_subscribers) >= MAX_SUBSCRIBERS:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many log stream connections"}
        )
    
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
