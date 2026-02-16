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


@router.get("/devices")
async def syncthing_devices():
    """Get Syncthing configured devices."""
    if not SYNCTHING_KEY:
        return {"configured": False, "devices": []}
    try:
        r = requests.get(
            f"{SYNCTHING_URL}/rest/system/config",
            headers={"X-API-Key": SYNCTHING_KEY},
            timeout=5,
        )
        config = r.json()
        
        # Get this device's ID to exclude it
        status_r = requests.get(
            f"{SYNCTHING_URL}/rest/system/status",
            headers={"X-API-Key": SYNCTHING_KEY},
            timeout=5,
        )
        my_id = status_r.json().get("myID", "")
        
        devices = []
        for d in config.get("devices", []):
            if d["deviceID"] == my_id:
                continue  # Skip self
            
            # Get connection status
            try:
                conn_r = requests.get(
                    f"{SYNCTHING_URL}/rest/system/connections",
                    headers={"X-API-Key": SYNCTHING_KEY},
                    timeout=5,
                )
                connections = conn_r.json().get("connections", {})
                conn_info = connections.get(d["deviceID"], {})
                connected = conn_info.get("connected", False)
            except Exception:
                connected = False
            
            devices.append({
                "id": d["deviceID"],
                "name": d.get("name", d["deviceID"][:8]),
                "connected": connected,
            })
        
        return {"configured": True, "devices": devices}
    except Exception as e:
        return {"configured": True, "error": str(e), "devices": []}


@router.get("/folder/{folder_id}/devices")
async def syncthing_folder_devices(folder_id: str):
    """Get which devices a specific folder is shared with."""
    if not SYNCTHING_KEY:
        return {"configured": False, "devices": []}
    try:
        r = requests.get(
            f"{SYNCTHING_URL}/rest/system/config",
            headers={"X-API-Key": SYNCTHING_KEY},
            timeout=5,
        )
        config = r.json()
        
        # Find the folder
        folder = None
        for f in config.get("folders", []):
            if f["id"] == folder_id:
                folder = f
                break
        
        if not folder:
            return {"error": f"Folder {folder_id} not found", "devices": []}
        
        # Get device names
        device_map = {d["deviceID"]: d.get("name", d["deviceID"][:8]) for d in config.get("devices", [])}
        
        shared_devices = []
        for fd in folder.get("devices", []):
            did = fd["deviceID"]
            if did in device_map:
                shared_devices.append({
                    "id": did,
                    "name": device_map[did],
                })
        
        return {"configured": True, "folder_id": folder_id, "devices": shared_devices}
    except Exception as e:
        return {"configured": True, "error": str(e), "devices": []}
