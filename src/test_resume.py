import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add current directory to path so we can import src
sys.path.insert(0, str(Path(__file__).parent.parent))

# Add bin to path for ffmpeg
os.environ["PATH"] = str(Path("bin").resolve()) + os.pathsep + os.environ["PATH"]

# Load env vars
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO)

from src.worker.processor import JobProcessor

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/test_resume.py <job_id>")
        sys.exit(1)
        
    job_id = sys.argv[1]
    
    config_dir = Path("config").resolve()
    processing_dir = Path("processing").resolve()
    output_dir = Path("output").resolve()
    
    # Check DB for filename
    from sqlmodel import Session, create_engine, select
    from src.api.models import Job
    DB_URL = "sqlite:///data/jobs.db"
    engine = create_engine(DB_URL)
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            print(f"Job Filename in DB: {job.filename}")
            if not Path(job.filename).exists():
                print(f"File missing at: {job.filename}")
        else:
            print(f"Job {job_id} not found locally")

    processor = JobProcessor(config_dir, processing_dir, output_dir)
    print(f"Resuming Job ID: {job_id}")
    processor.process_job(job_id)

if __name__ == "__main__":
    main()
