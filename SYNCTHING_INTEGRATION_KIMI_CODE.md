# Syncthing Integration — Claude Code Implementation

Apply all changes in order.

---

## BUG FIX: Syncthing field name mismatch in profiles route

The `list_profiles` endpoint accesses `profile.syncthing.folder` but the `SyncthingConfig` dataclass field is `share_folder`. This is currently causing an AttributeError that gets silently swallowed.

In `src/api/routes/profiles.py`, in the `list_profiles` function, find:

```python
                syncthing_folder=profile.syncthing.folder if profile.syncthing else None,
                syncthing_subfolder=profile.syncthing.subfolder if profile.syncthing else None,
```

Replace with:

```python
                syncthing_folder=profile.syncthing.share_folder if profile.syncthing else None,
                syncthing_subfolder=profile.syncthing.subfolder if profile.syncthing else None,
```

---

## CHANGE 1: Add folder_map management to ProfileLoader

The ProfileLoader already reads folder_map.yaml but has no way to write to it. We need add/remove methods so the profile creation flow can auto-register inbound folder mappings.

In `src/worker/profile_loader.py`, add these two methods to the `ProfileLoader` class, after the existing `get_profile_for_folder` method:

```python
    def add_folder_mapping(self, folder_name: str, profile_id: str):
        """Add a folder → profile mapping and persist to disk.
        
        Args:
            folder_name: The inbound folder name (e.g., 'data_protection')
            profile_id: The profile ID to map to
        """
        self._folder_map[folder_name.lower()] = profile_id
        self._save_folder_map()
        logger.info(f"Added folder mapping: {folder_name} → {profile_id}")
    
    def remove_folder_mapping(self, folder_name: str):
        """Remove a folder → profile mapping and persist to disk.
        
        Args:
            folder_name: The inbound folder name to remove
        """
        key = folder_name.lower()
        if key in self._folder_map:
            del self._folder_map[key]
            self._save_folder_map()
            logger.info(f"Removed folder mapping: {folder_name}")
    
    def _save_folder_map(self):
        """Write the current folder_map back to disk."""
        map_file = self.profiles_dir / "folder_map.yaml"
        try:
            data = {"folder_map": dict(self._folder_map)}
            with open(map_file, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.error(f"Failed to save folder map: {e}")
    
    def get_folder_map(self) -> dict:
        """Return the current folder → profile mapping."""
        return dict(self._folder_map)
```

---

## CHANGE 2: Auto-register folder mapping on profile create/delete

In `src/api/routes/profiles.py`:

### 2a. In `create_profile`, after the profile_loader.reload() call and before the get_profile check, add folder mapping:

Find:
```python
        # 6. Reload profile_loader
        profile_loader.reload()
        
        # 7. Return the new profile
```

Replace with:
```python
        # 6. Reload profile_loader
        profile_loader.reload()
        
        # 6b. Auto-register inbound folder mapping
        # Maps the profile ID as a folder name so files dropped in
        # uploads/{profile_id}/ get routed to this profile automatically
        profile_loader.add_folder_mapping(request.id, request.id)
        
        # 7. Return the new profile
```

### 2b. In `delete_profile`, after the profile_loader.reload() call, remove the folder mapping:

Find (at the end of `delete_profile`):
```python
    # 4. Reload the ProfileLoader
    profile_loader.reload()
```

Replace with:
```python
    # 4. Reload the ProfileLoader (clears stale entries due to our fix)
    profile_loader.reload()
    
    # 5. Remove inbound folder mapping
    profile_loader.remove_folder_mapping(profile_id)
```

---

## CHANGE 3: Add folder_map API endpoint

In `src/api/routes/profiles.py`, add this new endpoint at the end of the file, after the `update_stage_prompt` endpoint:

```python
@router.get("/folder-map", response_model=dict)
async def get_folder_map(
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """Get the current inbound folder → profile mapping."""
    return {"folder_map": profile_loader.get_folder_map()}


@router.put("/folder-map/{folder_name}")
async def set_folder_mapping(
    folder_name: str,
    body: dict,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """Set or update a folder → profile mapping.
    
    Body: {"profile_id": "some_profile"}
    """
    profile_id = body.get("profile_id")
    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id is required")
    
    profile_loader.add_folder_mapping(folder_name, profile_id)
    return {"folder": folder_name, "profile_id": profile_id}


@router.delete("/folder-map/{folder_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder_mapping(
    folder_name: str,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """Remove a folder → profile mapping."""
    profile_loader.remove_folder_mapping(folder_name)
```

---

## CHANGE 4: Enhance Syncthing routes with device info

In `src/api/routes/syncthing.py`, add a devices endpoint so the frontend can show friendly names. Add this at the end of the file:

```python
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
```

---

## CHANGE 5: Update Create Profile Modal with Syncthing folder picker

In `frontend/src/ControlHub.jsx`, update the `CreateProfileModal` component.

### 5a. Add state for Syncthing folders at the top of `CreateProfileModal`:

Find (inside `CreateProfileModal`, after the existing useState declarations):
```javascript
  const [syncthingFolder, setSyncthingFolder] = useState("");
  const [syncthingSubfolder, setSyncthingSubfolder] = useState("");
```

Replace with:
```javascript
  const [syncthingFolder, setSyncthingFolder] = useState("");
  const [syncthingSubfolder, setSyncthingSubfolder] = useState("");
  const [syncthingFolders, setSyncthingFolders] = useState([]);
  const [syncthingLoading, setSyncthingLoading] = useState(false);
  const [syncthingConfigured, setSyncthingConfigured] = useState(false);

  // Fetch Syncthing folders on mount
  useEffect(() => {
    setSyncthingLoading(true);
    apiFetch("/api/syncthing/folders")
      .then(data => {
        setSyncthingConfigured(data?.configured || false);
        if (data?.folders) {
          setSyncthingFolders(data.folders);
        }
      })
      .catch(() => setSyncthingConfigured(false))
      .finally(() => setSyncthingLoading(false));
  }, []);
```

You will also need to add `useEffect` to the existing import at the top of ControlHub.jsx if it's not already there. Check the first line — it should already have:
```javascript
import { useState, useEffect, useCallback, useRef } from "react";
```

### 5b. Replace the Syncthing folder input fields with a dropdown picker

Find the Syncthing section in step 1 of the modal:
```jsx
              {/* Syncthing output routing */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div>
                  <label style={labelStyle}>Syncthing Folder</label>
                  <input
                    value={syncthingFolder}
                    onChange={e => setSyncthingFolder(e.target.value)}
                    placeholder="e.g. keira-docs (optional)"
                    style={inputStyle}
                  />
                </div>
                <div>
                  <label style={labelStyle}>Subfolder</label>
                  <input
                    value={syncthingSubfolder}
                    onChange={e => setSyncthingSubfolder(e.target.value)}
                    placeholder="e.g. lectures"
                    style={inputStyle}
                  />
                </div>
              </div>
```

Replace with:
```jsx
              {/* Syncthing output routing */}
              <div>
                <label style={labelStyle}>Sync Output To</label>
                {syncthingLoading ? (
                  <div style={{ fontSize: 12, color: "rgba(255,255,255,0.3)", padding: "8px 0" }}>
                    Checking Syncthing...
                  </div>
                ) : !syncthingConfigured ? (
                  <div style={{
                    fontSize: 12, color: "rgba(255,255,255,0.25)", padding: "10px 14px",
                    background: "rgba(255,255,255,0.02)", borderRadius: 10,
                    border: "1px solid rgba(255,255,255,0.04)",
                  }}>
                    Syncthing not configured — outputs will stay on the server in <code style={{ color: "#a5b4fc" }}>outputs/docs/</code>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                      <div>
                        <select
                          value={syncthingFolder}
                          onChange={e => setSyncthingFolder(e.target.value)}
                          style={{ ...inputStyle, cursor: "pointer" }}
                        >
                          <option value="" style={{ background: "#1a1a2e" }}>No sync (local only)</option>
                          {syncthingFolders.map(f => (
                            <option key={f.id} value={f.id} style={{ background: "#1a1a2e" }}>
                              {f.label || f.id} {f.state === "syncing" ? " (syncing)" : ""}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <input
                          value={syncthingSubfolder}
                          onChange={e => setSyncthingSubfolder(e.target.value)}
                          placeholder="Subfolder (optional)"
                          style={inputStyle}
                          disabled={!syncthingFolder}
                        />
                      </div>
                    </div>
                    {syncthingFolder && (
                      <div style={{
                        fontSize: 11, color: "rgba(255,255,255,0.3)",
                        display: "flex", alignItems: "center", gap: 6,
                      }}>
                        <span style={{ color: "#34d399" }}>↗</span>
                        Output syncs to: <code style={{ color: "#a5b4fc" }}>
                          {syncthingFolders.find(f => f.id === syncthingFolder)?.label || syncthingFolder}
                          {syncthingSubfolder ? `/${syncthingSubfolder}` : ""}
                        </code>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Output path preview */}
              {name && (
                <div style={{
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid rgba(255,255,255,0.04)",
                  borderRadius: 8, padding: "10px 14px",
                }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.3)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
                    Pipeline Flow
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "rgba(255,255,255,0.4)", flexWrap: "wrap" }}>
                    <code style={{ color: "#fbbf24", background: "rgba(251,191,36,0.08)", padding: "2px 6px", borderRadius: 4 }}>
                      uploads/{profileId || autoId(name)}/
                    </code>
                    <span>→</span>
                    <span style={{ color: "rgba(255,255,255,0.5)" }}>{stages.length} stage pipeline</span>
                    <span>→</span>
                    <code style={{ color: "#34d399", background: "rgba(52,211,153,0.08)", padding: "2px 6px", borderRadius: 4 }}>
                      {syncthingFolder
                        ? `${syncthingFolders.find(f => f.id === syncthingFolder)?.label || syncthingFolder}${syncthingSubfolder ? `/${syncthingSubfolder}` : ""}`
                        : `outputs/docs/${syncthingSubfolder || profileId || autoId(name)}/`
                      }
                    </code>
                  </div>
                </div>
              )}
```

---

## CHANGE 6: Show sync chain in Profile Detail view

In the `ProfileDetail` component in `ControlHub.jsx`, add sync info and the full pipeline flow.

### 6a. Add Syncthing folder detail fetching

At the top of the `ProfileDetail` function, after the existing state declarations, add:

```javascript
  const [syncDevices, setSyncDevices] = useState([]);

  useEffect(() => {
    if (profile.syncthing_folder) {
      apiFetch(`/api/syncthing/folder/${profile.syncthing_folder}/devices`)
        .then(data => {
          if (data?.devices) setSyncDevices(data.devices);
        })
        .catch(() => {});
    }
  }, [profile.syncthing_folder]);
```

### 6b. Replace the existing syncthing display with a richer version

Find:
```jsx
          {profile.syncthing_folder && (
            <div style={{
              display: "flex", alignItems: "center", gap: 8, marginTop: 8,
              fontSize: 12, color: "rgba(255,255,255,0.5)",
              background: "rgba(255,255,255,0.05)", padding: "4px 10px", borderRadius: 6,
              width: "fit-content", border: "1px solid rgba(255,255,255,0.05)"
            }}>
              <span style={{ fontWeight: 500 }}>Syncthing:</span>
              <code style={{ fontSize: 11, color: "#a5b4fc" }}>
                {profile.syncthing_folder}
                {profile.syncthing_subfolder ? ` / ${profile.syncthing_subfolder}` : ""}
              </code>
            </div>
          )}
```

Replace with:
```jsx
          {/* Pipeline flow summary */}
          <div style={{
            display: "flex", alignItems: "center", gap: 8, marginTop: 10,
            fontSize: 12, color: "rgba(255,255,255,0.4)",
            background: "rgba(255,255,255,0.03)", padding: "8px 12px", borderRadius: 8,
            border: "1px solid rgba(255,255,255,0.04)", flexWrap: "wrap",
          }}>
            <code style={{ color: "#fbbf24", fontSize: 11 }}>
              uploads/{profile.id}/
            </code>
            <span style={{ color: "rgba(255,255,255,0.15)" }}>→</span>
            <span>{profile.stages?.length || 0} stages</span>
            <span style={{ color: "rgba(255,255,255,0.15)" }}>→</span>
            {profile.syncthing_folder ? (
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <code style={{ color: "#34d399", fontSize: 11 }}>
                  {profile.syncthing_folder}
                  {profile.syncthing_subfolder ? `/${profile.syncthing_subfolder}` : ""}
                </code>
                {syncDevices.length > 0 && (
                  <span style={{ color: "rgba(255,255,255,0.25)", fontSize: 11 }}>
                    → {syncDevices.map(d => d.name).join(", ")}
                  </span>
                )}
              </span>
            ) : (
              <code style={{ color: "#a5b4fc", fontSize: 11 }}>
                outputs/docs/{profile.syncthing_subfolder || profile.id}/
              </code>
            )}
          </div>
```

---

## CHANGE 7: Show sync status on Profile Cards

In the `ProfileCard` component, update the bottom stats line to show sync target.

Find:
```jsx
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
            {profile.stage_count} stage{profile.stage_count !== 1 ? "s" : ""} · {jobCount} job{jobCount !== 1 ? "s" : ""}
          </span>
```

Replace with:
```jsx
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
            {profile.stage_count} stage{profile.stage_count !== 1 ? "s" : ""} · {jobCount} job{jobCount !== 1 ? "s" : ""}
            {profile.syncthing_folder && (
              <span style={{ color: "rgba(52,211,153,0.4)" }}> · ↗ synced</span>
            )}
          </span>
```

---

## Verification

After applying all changes:

1. `cd frontend && npm run build`
2. `docker compose build app worker`
3. `docker compose up -d`

Test:
- Open Control Hub → click "+ New Profile"
- The Syncthing section should show a dropdown of your existing Syncthing folders (or a "not configured" message if SYNCTHING_API_KEY isn't set)
- Select a folder → see the pipeline flow preview update showing the full chain
- Create the profile → verify `config/profiles/folder_map.yaml` now includes the new mapping
- View a profile detail → see the full flow: uploads/{id}/ → stages → sync target → devices
- Delete a profile → verify the folder_map entry is removed
- Profile cards should show a "↗ synced" indicator for profiles with Syncthing configured
