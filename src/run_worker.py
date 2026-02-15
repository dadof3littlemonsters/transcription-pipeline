#!/usr/bin/env python3
# Note: Run with .venv/bin/python if available
# or activate venv: source .venv/bin/activate

import sys
import time
import logging
from pathlib import Path
from sqlmodel import Session, create_engine, select
import signal
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.api.models import Job, StageResult
from src.worker.processor import JobProcessor

# Load env vars
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/worker.log")
    ]
)
logger = logging.getLogger("worker")

DB_URL = "sqlite:///data/jobs.db"
engine = create_engine(DB_URL)

def get_next_job():
    """Get the next QUEUED job from the database."""
    with Session(engine) as session:
        statement = select(Job).where(Job.status == "QUEUED").order_by(Job.created_at).limit(1)
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
                # We don't reset stage results - we want to resume!
                session.add(job)
                logger.info(f"Reset Job ID {job.id} to QUEUED (will resume from last stage)")
            session.commit()

def run_worker():
    """Main worker loop."""
    # Add local bin to PATH for ffmpeg
    os.environ["PATH"] = str(Path("bin").resolve()) + os.pathsep + os.environ["PATH"]
    
    config_dir = Path("config").resolve()
    processing_dir = Path("processing").resolve()
    output_dir = Path("output").resolve()
    
    # Ensure logs dir exists
    Path("logs").mkdir(exist_ok=True)
    
    logger.info("Initializing worker...")
    try:
        # Reset any stuck jobs from previous runs
        reset_stuck_jobs()
        
        processor = JobProcessor(config_dir, processing_dir, output_dir)
        logger.info("Worker initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize worker: {e}")
        return

    logger.info("Starting worker loop. Press Ctrl+C to stop.")
    
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
                logger.info(f"Processing Job ID: {job.id} (File: {job.original_filename})")
                processor.process_job(job.id)
                logger.info(f"Finished Job ID: {job.id}")
            else:
                # Sleep if no jobs
                time.sleep(5)
        except Exception as e:
            logger.error(f"Error in worker loop: {e}")
            time.sleep(5) # Wait before retrying

if __name__ == "__main__":
    run_worker()
