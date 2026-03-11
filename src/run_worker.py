#!/usr/bin/env python3
"""Database-queue worker for the transcription pipeline."""

import os
import sys
import time
import logging
import signal
from pathlib import Path
from datetime import datetime

from sqlmodel import Session, create_engine, select
from dotenv import load_dotenv

# Imports must use src. prefix to match the rest of the codebase
from src.api.models import Job, StageResult
from src.worker.processor import JobProcessor

# Load env vars
load_dotenv()

# Configure logging to stdout (Docker captures this)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("worker")

DB_URL = "sqlite:///data/jobs.db"
engine = create_engine(DB_URL)


def get_next_job():
    """Get the next QUEUED job from the database, respecting priority."""
    with Session(engine) as session:
        statement = (
            select(Job)
            .where(Job.status == "QUEUED")
            .order_by(Job.priority.asc(), Job.created_at.asc())
            .limit(1)
        )
        return session.exec(statement).first()


def reset_stuck_jobs():
    """Reset jobs that were left in PROCESSING state (e.g., due to crash)."""
    with Session(engine) as session:
        statement = select(Job).where(Job.status == "PROCESSING")
        stuck_jobs = session.exec(statement).all()
        
        if stuck_jobs:
            logger.warning(f"Found {len(stuck_jobs)} stuck jobs. Resetting to QUEUED.")
            for job in stuck_jobs:
                job.status = "QUEUED"
                session.add(job)
                logger.info(f"Reset Job ID {job.id} to QUEUED (will resume from last stage)")
            session.commit()


def run_worker():
    """Main worker loop."""
    config_dir = Path("config").resolve()
    processing_dir = Path("processing").resolve()
    output_dir = Path("outputs").resolve()
    
    # Ensure directories exist
    Path("logs").mkdir(exist_ok=True)
    processing_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    
    logger.info("Initializing worker...")
    try:
        reset_stuck_jobs()
        processor = JobProcessor(config_dir, processing_dir, output_dir)
        logger.info("Worker initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize worker: {e}", exc_info=True)
        return

    logger.info("Starting worker loop. Polling for jobs every 5 seconds.")
    
    running = True
    def signal_handler(sig, frame):
        nonlocal running
        logger.info("Shutting down worker...")
        running = False
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    while running:
        try:
            job = get_next_job()
            if job:
                logger.info(f"Processing Job ID: {job.id} (File: {job.filename})")
                processor.process_job(job.id)
                logger.info(f"Finished Job ID: {job.id}")
            else:
                time.sleep(5)
        except Exception as e:
            logger.error(f"Error in worker loop: {e}", exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    run_worker()
