import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_update_profile(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        "/api/v1/users/profile",
        headers=auth_headers,
        json={"full_name": "Updated Name", "target_role": "Backend Developer", "experience_years": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["full_name"] == "Updated Name"
    assert data["target_role"] == "Backend Developer"
    assert data["experience_years"] == 3


@pytest.mark.asyncio
async def test_list_resumes_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/resumes/", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_interview(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/interviews/",
        headers=auth_headers,
        json={"target_role": "Software Engineer", "language": "english"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["target_role"] == "Software Engineer"
    assert data["status"] == "scheduled"
    assert data["current_phase"] == "introduction"
    assert data["difficulty_level"] == 5.0


@pytest.mark.asyncio
async def test_list_interviews(client: AsyncClient, auth_headers: dict):
    # Create two interviews
    await client.post("/api/v1/interviews/", headers=auth_headers, json={"target_role": "Frontend Dev"})
    await client.post("/api/v1/interviews/", headers=auth_headers, json={"target_role": "Backend Dev"})

    resp = await client.get("/api/v1/interviews/", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_get_interview_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/interviews/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_report_before_completion(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/interviews/",
        headers=auth_headers,
        json={"target_role": "Data Scientist"},
    )
    interview_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/reports/{interview_id}/generate",
        headers=auth_headers,
    )
    assert resp.status_code == 400  # Interview not completed yet


@pytest.mark.asyncio
async def test_unauthorized_access(client: AsyncClient):
    resp = await client.get("/api/v1/interviews/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_access_denied_for_student(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/admin/users", headers=auth_headers)
    assert resp.status_code == 403
