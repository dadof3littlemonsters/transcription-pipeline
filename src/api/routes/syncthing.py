"""
Syncthing API proxy routes.
"""

import os
import requests
from fastapi import APIRouter

router = APIRouter(prefix="/api/syncthing", tags=["Syncthing"])

SYNCTHING_URL = os.getenv("SYNCTHING_URL", "http://localhost:8384")
SYNCTHING_KEY = os.getenv("SYNCTHING_API_KEY", "")


@router.get("/status")
async def syncthing_status():
    """Get Syncthing system status."""
    if not SYNCTHING_KEY:
        return {"configured": False}
    try:
        r = requests.get(
            f"{SYNCTHING_URL}/rest/system/status",
            headers={"X-API-Key": SYNCTHING_KEY},
            timeout=5,
        )
        return {"configured": True, "status": r.json()}
    except Exception as e:
        return {"configured": True, "error": str(e)}


@router.get("/folders")
async def syncthing_folders():
    """Get Syncthing folder status."""
    if not SYNCTHING_KEY:
        return {"configured": False, "folders": []}
    try:
        r = requests.get(
            f"{SYNCTHING_URL}/rest/system/config",
            headers={"X-API-Key": SYNCTHING_KEY},
            timeout=5,
        )
        config = r.json()
        folders = []
        for f in config.get("folders", []):
            # Get completion for each folder
            try:
                comp = requests.get(
                    f"{SYNCTHING_URL}/rest/db/completion?folder={f['id']}",
                    headers={"X-API-Key": SYNCTHING_KEY},
                    timeout=5,
                ).json()
            except Exception:
                comp = {}
            folders.append({
                "id": f["id"],
                "label": f.get("label", f["id"]),
                "path": f["path"],
                "completion": comp.get("completion", 0),
                "state": "synced" if comp.get("completion", 0) >= 100 else "syncing",
            })
        return {"configured": True, "folders": folders}
    except Exception as e:
        return {"configured": True, "error": str(e), "folders": []}
