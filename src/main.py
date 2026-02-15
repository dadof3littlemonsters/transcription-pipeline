"""
Main entry point for the transcription pipeline API server.
"""

import asyncio
import logging
import os
import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import redis.asyncio as aioredis
import json
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, create_engine

from src.api.routes import jobs_router, profiles_router
from src.api.dependencies import validate_api_keys
from src.api.schemas import HealthCheckResponse, ReadinessCheckResponse
from src.api.websocket import manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Structured JSON logging for production
if os.getenv("LOG_FORMAT", "").lower() == "json":
    import json as json_mod
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            return json_mod.dumps({
                "timestamp": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            })
    for handler in logging.root.handlers:
        handler.setFormatter(JSONFormatter())

# Database configuration
DB_URL = "sqlite:///data/jobs.db"
engine = create_engine(DB_URL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Transcription Pipeline API...")
    
    # Ensure database tables exist
    SQLModel.metadata.create_all(engine)
    
    # Ensure required directories exist
    for directory in ["uploads", "processing", "output", "data", "logs"]:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    # Start Redis listener for WebSocket broadcasting
    redis_task = asyncio.create_task(redis_listener())
    
    yield
    
    redis_task.cancel()
    try:
        await redis_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down Transcription Pipeline API...")


async def redis_listener():
    """Subscribe to Redis job_updates channel and broadcast via WebSocket."""
    while True:
        try:
            r = aioredis.Redis(host="redis", port=6379)
            pubsub = r.pubsub()
            await pubsub.subscribe("job_updates")
            logger.info("Redis listener subscribed to job_updates")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    await manager.broadcast("job_update", data)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Redis listener error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)


# Create FastAPI application
app = FastAPI(
    title="Transcription Pipeline API",
    description="A scalable audio/video transcription service with multi-stage processing",
    version="2.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://transcribe.delboysden.uk",
        "http://localhost:5173",
        "http://localhost:8888",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Slowapi rate limiting error handler
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include routers
app.include_router(jobs_router)
app.include_router(profiles_router)

from src.api.routes.syncthing import router as syncthing_router
app.include_router(syncthing_router)

from src.api.routes.costs import router as costs_router
app.include_router(costs_router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time job updates."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/health", response_model=HealthCheckResponse, tags=["General"])
async def health_check():
    """
    Health check endpoint.
    
    Checks database connectivity, disk space, and worker status.
    """
    checks = {
        "api": True,
        "database": False,
        "disk_space": False,
    }
    
    # Check database
    try:
        from sqlmodel import Session, select
        from src.api.models import Job
        with Session(engine) as session:
            # Simple query to verify DB is accessible
            session.exec(select(Job).limit(1)).first()
        checks["database"] = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
    
    # Check disk space (require at least 1GB free)
    try:
        stat = shutil.disk_usage(".")
        free_gb = stat.free / (1024 ** 3)
        checks["disk_space"] = free_gb > 1.0
    except Exception as e:
        logger.error(f"Disk space check failed: {e}")
    
    overall_status = "healthy" if all(checks.values()) else "degraded"
    
    return HealthCheckResponse(
        status=overall_status,
        service="transcription-pipeline",
        checks=checks,
        timestamp=datetime.now(),
    )


@app.get("/ready", response_model=ReadinessCheckResponse, tags=["General"])
async def readiness_check():
    """
    Readiness check endpoint.
    
    Checks if the service is ready to accept requests (API keys configured, etc.).
    """
    checks = {
        "api": True,
    }
    
    # Check API keys
    api_keys = validate_api_keys()
    checks.update(api_keys)
    
    missing_keys = [k for k, v in api_keys.items() if not v]
    
    return ReadinessCheckResponse(
        ready=all(checks.values()),
        checks=checks,
        missing_keys=missing_keys if missing_keys else None,
    )


# Mount static files for frontend (must be AFTER all API routes)
from fastapi.staticfiles import StaticFiles
import pathlib

frontend_dist = pathlib.Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
    logger.info(f"Mounted frontend static files from {frontend_dist}")
else:
    logger.warning(f"Frontend dist directory not found at {frontend_dist}")



if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=os.getenv("DEBUG", "false").lower() == "true",
    )
