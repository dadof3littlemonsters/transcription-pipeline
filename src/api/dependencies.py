"""
Dependency injection utilities for FastAPI.
"""

import os
from pathlib import Path
from typing import Generator, Dict, Optional

from sqlmodel import Session, create_engine
from fastapi import Depends, HTTPException, status

from src.api.models import Job
from src.worker.profile_loader import ProfileLoader

# Database configuration
DB_URL = "sqlite:///data/jobs.db"
engine = create_engine(DB_URL)


def get_db_session() -> Generator[Session, None, None]:
    """Dependency to get database session."""
    with Session(engine) as session:
        yield session


def get_profile_loader() -> ProfileLoader:
    """Dependency to get ProfileLoader instance."""
    config_dir = Path("config").resolve()
    return ProfileLoader(config_dir)


def validate_api_keys() -> Dict[str, bool]:
    """Check which API keys are configured."""
    return {
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "deepseek": bool(os.getenv("DEEPSEEK_API_KEY")),
        "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "zai": bool(os.getenv("ZAI_API_KEY")),
        "huggingface": bool(os.getenv("HUGGINGFACE_TOKEN")),
    }


def require_api_keys():
    """Dependency that raises error if minimum required API keys are missing.
    
    Requires: Groq + at least one LLM provider (deepseek/openrouter/openai/zai).
    """
    keys = validate_api_keys()
    
    missing = []
    if not keys["groq"]:
        missing.append("GROQ_API_KEY")
    
    llm_providers = ["deepseek", "openrouter", "openai", "zai"]
    if not any(keys[p] for p in llm_providers):
        missing.append("At least one LLM key (DEEPSEEK/OPENROUTER/OPENAI/ZAI)")
    
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unavailable: Missing API keys: {', '.join(missing)}"
        )


# Optional API key auth
PIPELINE_API_KEY = os.getenv("PIPELINE_API_KEY", "")


async def verify_api_key(
    x_api_key: Optional[str] = None,
):
    """
    Verify the X-API-Key header if PIPELINE_API_KEY is set.
    If PIPELINE_API_KEY is empty, auth is disabled (development mode).
    """
    if PIPELINE_API_KEY and x_api_key != PIPELINE_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

