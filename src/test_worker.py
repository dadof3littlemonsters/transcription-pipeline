import sys
import os
from pathlib import Path
from sqlmodel import Session, create_engine

from dotenv import load_dotenv

# Add current directory to path so we can import src
sys.path.insert(0, str(Path(__file__).parent.parent))

# Add bin to path for ffmpeg
os.environ["PATH"] = str(Path("bin").resolve()) + os.pathsep + os.environ["PATH"]

# Load env vars
load_dotenv()

from src.api.models import Job
from src.worker.processor import JobProcessor

DB_URL = "sqlite:///data/jobs.db"
engine = create_engine(DB_URL)

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/test_worker.py <audio_file> [profile_id]")
        print("  profile_id: social_work_lecture, business_lecture (optional)")
        sys.exit(1)
    
    audio_file = Path(sys.argv[1]).resolve()
    profile_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not audio_file.exists():
        print(f"Error: File not found: {audio_file}")
        sys.exit(1)
        
    print(f"Testing worker with: {audio_file}")
    if profile_id:
        print(f"Profile: {profile_id}")
    
    # Create Job
    with Session(engine) as session:
        job = Job(
            filename=str(audio_file),
            original_filename=audio_file.name,
            profile_id=profile_id,
            status="QUEUED"
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        print(f"Created Job ID: {job.id}")
        
        job_id = job.id

    # Run Processor
    config_dir = Path("config").resolve()
    processing_dir = Path("processing").resolve()
    output_dir = Path("output").resolve()
    
    processor = JobProcessor(config_dir, processing_dir, output_dir)
    
    try:
        print("Starting processing...")
        processor.process_job(job_id)
        print("Processing finished.")
        
        # Check result
        with Session(engine) as session:
            job = session.get(Job, job_id)
            print(f"Final Job Status: {job.status}")
            if job.error:
                print(f"Error: {job.error}")
    except Exception as e:
        print(f"Execution failed: {e}")

if __name__ == "__main__":
    main()
