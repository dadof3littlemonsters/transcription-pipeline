"""API routes package."""

from src.api.routes.jobs import router as jobs_router
from src.api.routes.profiles import router as profiles_router

__all__ = ["jobs_router", "profiles_router"]
