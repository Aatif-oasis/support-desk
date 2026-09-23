"""
API key management for the Integrations screen: create, list (secret
never shown again), and revoke (immediate, no grace period).
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _register_org(client: AsyncClient, org_name: str, email: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": org_name,
            "admin_full_name": "Admin Person",
            "admin_email": email,
            "admin_password": "SuperSecret123",
        },
    )
    return resp.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_created_key_is_listed_without_its_secret(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Keys Org", unique_email)
    admin = _auth(tokens["access_token"])

    created = await client.post(
        "/api/v1/auth/api-keys", json={"name": "CRM Integration", "scopes": []}, headers=admin
    )
    assert created.status_code == 201, created.text
    assert created.json()["api_key"].startswith("oc_live_")

    listed = await client.get("/api/v1/auth/api-keys", headers=admin)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["name"] == "CRM Integration"
    assert "api_key" not in rows[0]


async def test_revoked_key_stops_authenticating(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Revoke Org", unique_email)
    admin = _auth(tokens["access_token"])

    created = await client.post(
        "/api/v1/auth/api-keys", json={"name": "To Revoke", "scopes": []}, headers=admin
    )
    key_id = created.json()["id"]
    plaintext = created.json()["api_key"]

    still_works = await client.get(
        "/api/v1/integration/ping", headers={"X-API-Key": plaintext}
    )
    assert still_works.status_code == 200, still_works.text

    revoked = await client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=admin)
    assert revoked.status_code == 204

    after = await client.get("/api/v1/integration/ping", headers={"X-API-Key": plaintext})
    assert after.status_code == 401, after.text

    listed = await client.get("/api/v1/auth/api-keys", headers=admin)
    assert listed.json() == []


async def test_an_agent_cannot_manage_api_keys(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Locked Keys Org", unique_email)
    admin = _auth(tokens["access_token"])
    await client.post("/api/v1/users", json={
        "email": "nosy3.agent@example.com",
        "full_name": "Nosy Agent",
        "temporary_password": "AgentPass123",
        "role": "agent",
    }, headers=admin)
    agent = _auth((await client.post(
        "/api/v1/auth/login",
        json={"email": "nosy3.agent@example.com", "password": "AgentPass123"},
    )).json()["access_token"])

    resp = await client.post("/api/v1/auth/api-keys", json={"name": "x", "scopes": []}, headers=agent)
    assert resp.status_code == 403
