"""Deprecated worker entrypoint.

This module is kept for backward compatibility with older commands
(e.g. `python src/worker.py`). The active worker architecture is the
DB-queue worker in `src.run_worker`.
"""

import logging

from src.run_worker import run_worker as run_db_queue_worker

logger = logging.getLogger("worker-deprecated")


def run_worker():
    """Run the active DB-queue worker (compat shim)."""
    logger.warning(
        "src/worker.py is deprecated; forwarding to src.run_worker (DB queue mode)."
    )
    run_db_queue_worker()


if __name__ == "__main__":
    run_worker()
