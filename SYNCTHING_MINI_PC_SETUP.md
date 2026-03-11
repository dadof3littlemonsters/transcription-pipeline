# Mini PC + Syncthing Setup (Mirabox -> VPS)

## Goal

Record on mini PC, sync to VPS automatically, queue jobs automatically, sync outputs back to devices.

## 1) Mini PC folder structure

Create this tree on the mini PC:

```bash
mkdir -p ~/recordings/work/{meeting,supervision,client,braindump}
mkdir -p ~/recordings/lectures/{kate,keira}
```

Use these as recorder targets:

- Work recordings:
  - `~/recordings/work/meeting`
  - `~/recordings/work/supervision`
  - `~/recordings/work/client`
  - `~/recordings/work/braindump`
- Lectures:
  - `~/recordings/lectures/kate`
  - `~/recordings/lectures/keira`

## 2) VPS folder structure

In the pipeline repo on VPS:

```bash
mkdir -p sync_inbox/work/{meeting,supervision,client,braindump}
mkdir -p sync_inbox/lectures/{kate,keira}
mkdir -p sync_inbox/_ingested sync_inbox/_failed
```

## 3) Syncthing folder links

Create one Syncthing shared folder between mini PC and VPS for inbound recordings:

- Mini PC path: `~/recordings`
- VPS path: `/home/peptifit/transcription-pipeline/sync_inbox`

Recommended folder mode:

- Mini PC: `Send Only`
- VPS: `Receive Only`

Ignore patterns (set in Syncthing):

```text
(?d).DS_Store
(?d)Thumbs.db
(?d)*.tmp
(?d)*.part
(?d)*.crdownload
(?d)~$*
```

## 4) Ingest service (VPS)

The docker stack includes `ingester`, which:

- scans `/app/sync_inbox`
- maps folder names to pipeline profiles
- posts files to `/api/jobs`
- moves processed files to `_ingested` or `_failed`

Default mapping:

- `meeting -> meeting`
- `supervision -> supervision`
- `client -> client`
- `braindump -> braindump`
- `kate -> social_work_lecture`
- `keira -> business_lecture`

If needed, override in `.env`:

```bash
SYNC_INGEST_FOLDER_MAP=meeting:meeting,supervision:supervision,client:client,braindump:braindump,kate:social_work_lecture,keira:business_lecture
```

Legacy compatibility (no Kate/Keira device change required):

- `ingester` also scans:
  - `/app/uploads/kate`
  - `/app/uploads/keira`
- Legacy lecture files are processed in-place (not moved), deduped by hash.
- `uploads/work` is not part of the legacy scan. Work recordings should arrive in `sync_inbox/work/...`.
- Configure via:

```bash
SYNC_INGEST_LEGACY_DIRS=/app/uploads/kate,/app/uploads/keira
```

## 5) Start/restart services (VPS)

```bash
docker compose up -d --build app worker ingester
```

Check logs:

```bash
docker compose logs -f ingester
docker compose logs -f worker
```

Check ingester API status:

```bash
curl -s http://localhost:8888/api/ingester/status -H "X-API-Key: $PIPELINE_API_KEY" | jq
```

## 6) Output sync back to users

Keep outputs in Syncthing on VPS from:

- `/home/peptifit/transcription-pipeline/outputs/docs`

Profiles with `syncthing.subfolder` route docs into per-user subfolders:

- `social_work_lecture -> outputs/docs/kate`
- `business_lecture -> outputs/docs/keira`
- standard work notes -> `outputs/docs/work/{meeting,supervision,client,braindump}`

## 7) Daily operation

1. Mirabox saves recording to the correct mini-PC folder.
2. Syncthing sends file to VPS `sync_inbox/...`.
3. `ingester` queues a job.
4. `worker` processes job.
5. Outputs are written to `outputs/docs` (or subfolder).
6. Syncthing distributes outputs to user devices.
