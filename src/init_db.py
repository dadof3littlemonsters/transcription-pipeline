import sys
from pathlib import Path

# Add root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import SQLModel, create_engine
from src.api.models import Job, StageResult

DB_URL = "sqlite:///data/jobs.db"
engine = create_engine(DB_URL)

def init_db():
    print(f"Initializing database at {DB_URL}")
    SQLModel.metadata.create_all(engine)
    print("Database tables created.")

if __name__ == "__main__":
    init_db()
