"""
API endpoint tests for the transcription pipeline.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app


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
