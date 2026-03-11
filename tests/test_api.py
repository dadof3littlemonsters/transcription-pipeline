"""
API endpoint tests for the transcription pipeline.
"""

import pytest
from pathlib import Path
from uuid import uuid4
from httpx import AsyncClient, ASGITransport
from sqlmodel import Session, select

from src.main import app
from src.api.dependencies import engine
from src.api.models import Job


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] in ["healthy", "degraded"]


@pytest.mark.asyncio
async def test_ready(client):
    r = await client.get("/ready")
    assert r.status_code == 200
    assert "ready" in r.json()


@pytest.mark.asyncio
async def test_list_profiles(client):
    r = await client.get("/api/profiles")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_list_jobs(client):
    r = await client.get("/api/jobs")
    assert r.status_code == 200
    assert "jobs" in r.json()


@pytest.mark.asyncio
async def test_create_job_no_file(client):
    r = await client.post("/api/jobs", data={"profile_id": "meeting"})
    assert r.status_code == 422  # Missing file


@pytest.mark.asyncio
async def test_get_nonexistent_job(client):
    r = await client.get("/api/jobs/nonexistent-id")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_job(client):
    r = await client.delete("/api/jobs/nonexistent-id")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cost_summary(client):
    r = await client.get("/api/costs/summary")
    assert r.status_code == 200
    data = r.json()
    assert "total_cost" in data
    assert "by_profile" in data
    assert "job_count" in data


@pytest.mark.asyncio
async def test_get_job_outputs_robust_stem_matching(client):
    profile_id = f"test_profile_{uuid4().hex[:8]}"
    job_id = str(uuid4())
    fake_filename = "/tmp/uploads/2026-03-06-12-00-00_sync-conflict-20260306-120000-ABCD_weekly_team.mp3"

    output_file = Path("outputs/docs/weekly_team_clean.docx")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("dummy", encoding="utf-8")

    with Session(engine) as session:
        session.add(
            Job(
                id=job_id,
                profile_id=profile_id,
                filename=fake_filename,
                status="COMPLETE",
                priority=5,
            )
        )
        session.commit()

    try:
        r = await client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200
        data = r.json()
        outputs = data.get("outputs", [])
        assert any(o.get("name") == output_file.name for o in outputs)
    finally:
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job:
                session.delete(job)
                session.commit()
        output_file.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_list_jobs_total_uses_db_count_with_pagination(client):
    profile_id = f"count_profile_{uuid4().hex[:8]}"
    job_ids = [str(uuid4()) for _ in range(3)]

    with Session(engine) as session:
        for jid in job_ids:
            session.add(
                Job(
                    id=jid,
                    profile_id=profile_id,
                    filename=f"/tmp/uploads/{jid}.mp3",
                    status="QUEUED",
                    priority=5,
                )
            )
        session.commit()

    try:
        r = await client.get(f"/api/jobs?profile_id={profile_id}&limit=2&offset=0")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 3
        assert len(data["jobs"]) == 2
    finally:
        with Session(engine) as session:
            jobs = session.exec(select(Job).where(Job.profile_id == profile_id)).all()
            for job in jobs:
                session.delete(job)
            session.commit()
