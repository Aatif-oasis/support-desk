import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _register_org_admin(client: AsyncClient, email: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Test Org",
            "admin_full_name": "Admin Person",
            "admin_email": email,
            "admin_password": "SuperSecret123",
        },
    )
    return resp.json()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------- Departments ----------

async def test_org_admin_can_create_and_list_departments(client: AsyncClient, unique_email: str):
    tokens = await _register_org_admin(client, unique_email)
    headers = _auth_header(tokens["access_token"])

    create_resp = await client.post("/api/v1/departments", json={"name": "Support"}, headers=headers)
    assert create_resp.status_code == 201
    dept_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/departments", headers=headers)
    assert list_resp.status_code == 200
    assert any(d["id"] == dept_id for d in list_resp.json())


async def test_department_create_requires_org_admin_role(client: AsyncClient, unique_email: str):
    tokens = await _register_org_admin(client, unique_email)
    headers = _auth_header(tokens["access_token"])

    invite_resp = await client.post(
        "/api/v1/users",
        json={
            "email": f"agent-{unique_email}",
            "full_name": "Agent Person",
            "temporary_password": "TempPass123",
            "role": "agent",
        },
        headers=headers,
    )
    assert invite_resp.status_code == 201

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": f"agent-{unique_email}", "password": "TempPass123"},
    )
    agent_headers = _auth_header(login_resp.json()["access_token"])

    forbidden_resp = await client.post(
        "/api/v1/departments", json={"name": "Should Fail"}, headers=agent_headers
    )
    assert forbidden_resp.status_code == 403


# ---------- Teams ----------

async def test_team_creation_and_membership_lifecycle(client: AsyncClient, unique_email: str):
    tokens = await _register_org_admin(client, unique_email)
    headers = _auth_header(tokens["access_token"])

    team_resp = await client.post("/api/v1/teams", json={"name": "Tier 1"}, headers=headers)
    assert team_resp.status_code == 201
    team_id = team_resp.json()["id"]

    invite_resp = await client.post(
        "/api/v1/users",
        json={
            "email": f"member-{unique_email}",
            "full_name": "Member Person",
            "temporary_password": "TempPass123",
            "role": "agent",
        },
        headers=headers,
    )
    user_id = invite_resp.json()["id"]

    add_resp = await client.post(
        f"/api/v1/teams/{team_id}/members", json={"user_id": user_id}, headers=headers
    )
    assert add_resp.status_code == 204

    members_resp = await client.get(f"/api/v1/teams/{team_id}/members", headers=headers)
    assert members_resp.status_code == 200
    assert any(m["id"] == user_id for m in members_resp.json())

    remove_resp = await client.delete(
        f"/api/v1/teams/{team_id}/members/{user_id}", headers=headers
    )
    assert remove_resp.status_code == 204

    members_after = await client.get(f"/api/v1/teams/{team_id}/members", headers=headers)
    assert not any(m["id"] == user_id for m in members_after.json())


# ---------- Users ----------

async def test_invited_user_can_login_and_becomes_active(client: AsyncClient, unique_email: str):
    tokens = await _register_org_admin(client, unique_email)
    headers = _auth_header(tokens["access_token"])

    invite_email = f"newagent-{unique_email}"
    invite_resp = await client.post(
        "/api/v1/users",
        json={
            "email": invite_email,
            "full_name": "New Agent",
            "temporary_password": "TempPass123",
            "role": "agent",
        },
        headers=headers,
    )
    assert invite_resp.json()["status"] == "invited"

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": invite_email, "password": "TempPass123"}
    )
    assert login_resp.status_code == 200

    get_resp = await client.get(
        f"/api/v1/users/{invite_resp.json()['id']}", headers=headers
    )
    assert get_resp.json()["status"] == "active"


async def test_deactivated_user_cannot_login(client: AsyncClient, unique_email: str):
    tokens = await _register_org_admin(client, unique_email)
    headers = _auth_header(tokens["access_token"])

    invite_email = f"deactme-{unique_email}"
    invite_resp = await client.post(
        "/api/v1/users",
        json={
            "email": invite_email,
            "full_name": "Deact Me",
            "temporary_password": "TempPass123",
            "role": "agent",
        },
        headers=headers,
    )
    user_id = invite_resp.json()["id"]

    deactivate_resp = await client.delete(f"/api/v1/users/{user_id}", headers=headers)
    assert deactivate_resp.status_code == 204

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": invite_email, "password": "TempPass123"}
    )
    assert login_resp.status_code == 401


async def test_deactivating_user_immediately_revokes_existing_token(
    client: AsyncClient, unique_email: str
):
    """
    Proves deactivation takes effect immediately, not just on next login —
    an already-issued, unexpired access token must stop working right away.
    """
    tokens = await _register_org_admin(client, unique_email)
    admin_headers = _auth_header(tokens["access_token"])

    invite_email = f"revokeme-{unique_email}"
    invite_resp = await client.post(
        "/api/v1/users",
        json={
            "email": invite_email,
            "full_name": "Revoke Me",
            "temporary_password": "TempPass123",
            "role": "agent",
        },
        headers=admin_headers,
    )
    user_id = invite_resp.json()["id"]

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": invite_email, "password": "TempPass123"}
    )
    victim_token = login_resp.json()["access_token"]
    victim_headers = _auth_header(victim_token)

    # Confirm the token works before deactivation.
    pre_check = await client.get("/api/v1/departments", headers=victim_headers)
    assert pre_check.status_code == 200

    await client.delete(f"/api/v1/users/{user_id}", headers=admin_headers)

    post_check = await client.get("/api/v1/departments", headers=victim_headers)
    assert post_check.status_code == 401


async def test_duplicate_email_invite_returns_409(client: AsyncClient, unique_email: str):
    tokens = await _register_org_admin(client, unique_email)
    headers = _auth_header(tokens["access_token"])

    payload = {
        "email": f"dupe-{unique_email}",
        "full_name": "Dupe",
        "temporary_password": "TempPass123",
        "role": "agent",
    }
    first = await client.post("/api/v1/users", json=payload, headers=headers)
    assert first.status_code == 201

    second = await client.post("/api/v1/users", json=payload, headers=headers)
    assert second.status_code == 409


# ---------- Organizations (Super Admin only) ----------

async def test_org_admin_cannot_list_organizations(client: AsyncClient, unique_email: str):
    tokens = await _register_org_admin(client, unique_email)
    headers = _auth_header(tokens["access_token"])

    resp = await client.get("/api/v1/organizations", headers=headers)
    assert resp.status_code == 403
