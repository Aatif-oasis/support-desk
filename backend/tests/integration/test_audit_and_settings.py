import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _register_org(client: AsyncClient, org_name: str, email: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": org_name,
            "admin_full_name": "Admin",
            "admin_email": email,
            "admin_password": "SuperSecret123",
        },
    )
    return resp.json()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------- Audit Logs ----------

async def test_inviting_user_creates_audit_log(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Audit Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    agent_email = f"agent-{unique_email}"
    await client.post(
        "/api/v1/users",
        json={"email": agent_email, "full_name": "Agent", "temporary_password": "TempPass123", "role": "agent"},
        headers=headers,
    )

    logs_resp = await client.get("/api/v1/audit-logs", headers=headers)
    assert logs_resp.status_code == 200
    assert any(l["action"] == "user.invited" for l in logs_resp.json())


async def test_deactivate_and_role_assign_create_audit_logs(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Audit Org 2", unique_email)
    headers = _auth_header(tokens["access_token"])

    agent_email = f"agent-{unique_email}"
    invite_resp = await client.post(
        "/api/v1/users",
        json={"email": agent_email, "full_name": "Agent", "temporary_password": "TempPass123", "role": "agent"},
        headers=headers,
    )
    user_id = invite_resp.json()["id"]

    await client.post(f"/api/v1/users/{user_id}/roles", json={"role": "team_manager"}, headers=headers)
    await client.delete(f"/api/v1/users/{user_id}", headers=headers)

    logs_resp = await client.get("/api/v1/audit-logs", headers=headers)
    actions = [l["action"] for l in logs_resp.json()]
    assert "user.role_assigned" in actions
    assert "user.deactivated" in actions


async def test_agent_cannot_view_audit_logs(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Audit RBAC Org", unique_email)
    admin_headers = _auth_header(tokens["access_token"])

    agent_email = f"agent-{unique_email}"
    await client.post(
        "/api/v1/users",
        json={"email": agent_email, "full_name": "Agent", "temporary_password": "TempPass123", "role": "agent"},
        headers=admin_headers,
    )
    login = await client.post("/api/v1/auth/login", json={"email": agent_email, "password": "TempPass123"})
    agent_headers = _auth_header(login.json()["access_token"])

    resp = await client.get("/api/v1/audit-logs", headers=agent_headers)
    assert resp.status_code == 403


async def test_audit_logs_filter_by_action(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Audit Filter Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    await client.post(
        "/api/v1/auth/api-keys", json={"name": "Test Key", "scopes": []}, headers=headers
    )

    resp = await client.get("/api/v1/audit-logs?action=api_key.created", headers=headers)
    assert len(resp.json()) == 1
    assert resp.json()[0]["action"] == "api_key.created"


async def test_audit_logs_isolated_by_organization(client: AsyncClient, unique_email: str):
    tokens_a = await _register_org(client, "Audit Iso A", f"a-{unique_email}")
    tokens_b = await _register_org(client, "Audit Iso B", f"b-{unique_email}")

    await client.post(
        "/api/v1/users",
        json={"email": f"x-{unique_email}", "full_name": "X", "temporary_password": "TempPass123", "role": "agent"},
        headers=_auth_header(tokens_a["access_token"]),
    )

    logs_b = await client.get("/api/v1/audit-logs", headers=_auth_header(tokens_b["access_token"]))
    assert logs_b.json() == []


# ---------- Settings ----------

async def test_get_default_settings(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Settings Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    resp = await client.get("/api/v1/settings", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["theme_primary_color"] is None


async def test_update_settings_merges_not_overwrites(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Settings Merge Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    first = await client.patch(
        "/api/v1/settings", json={"theme_primary_color": "#FF5733"}, headers=headers
    )
    assert first.json()["theme_primary_color"] == "#FF5733"

    second = await client.patch(
        "/api/v1/settings", json={"widget_greeting_message": "Hi there!"}, headers=headers
    )
    # Second update must not erase the first field.
    assert second.json()["theme_primary_color"] == "#FF5733"
    assert second.json()["widget_greeting_message"] == "Hi there!"


async def test_invalid_color_format_rejected(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Settings Invalid Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    resp = await client.patch(
        "/api/v1/settings", json={"theme_primary_color": "not-a-color"}, headers=headers
    )
    assert resp.status_code == 422


async def test_agent_can_read_but_not_write_settings(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Settings RBAC Org", unique_email)
    admin_headers = _auth_header(tokens["access_token"])

    agent_email = f"agent-{unique_email}"
    await client.post(
        "/api/v1/users",
        json={"email": agent_email, "full_name": "Agent", "temporary_password": "TempPass123", "role": "agent"},
        headers=admin_headers,
    )
    login = await client.post("/api/v1/auth/login", json={"email": agent_email, "password": "TempPass123"})
    agent_headers = _auth_header(login.json()["access_token"])

    read_resp = await client.get("/api/v1/settings", headers=agent_headers)
    assert read_resp.status_code == 200

    write_resp = await client.patch(
        "/api/v1/settings", json={"widget_greeting_message": "nope"}, headers=agent_headers
    )
    assert write_resp.status_code == 403


async def test_settings_update_creates_audit_log(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Settings Audit Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    await client.patch("/api/v1/settings", json={"theme_primary_color": "#000000"}, headers=headers)

    logs_resp = await client.get("/api/v1/audit-logs?action=settings.updated", headers=headers)
    assert len(logs_resp.json()) == 1
