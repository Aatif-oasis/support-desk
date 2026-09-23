"""The one fact (name, slug) an org_admin needs for the widget snippet."""
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


async def test_org_admin_reads_their_own_slug(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Widget Setup Org", unique_email)
    admin = _auth(tokens["access_token"])

    resp = await client.get("/api/v1/my-organization", headers=admin)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Widget Setup Org"
    assert resp.json()["slug"] == "widget-setup-org"


async def test_an_agent_also_reads_their_own_slug(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Agent Slug Org", unique_email)
    admin = _auth(tokens["access_token"])
    await client.post("/api/v1/users", json={
        "email": "widgetslug.agent@example.com",
        "full_name": "Slug Agent",
        "temporary_password": "AgentPass123",
        "role": "agent",
    }, headers=admin)
    agent = _auth((await client.post(
        "/api/v1/auth/login",
        json={"email": "widgetslug.agent@example.com", "password": "AgentPass123"},
    )).json()["access_token"])

    resp = await client.get("/api/v1/my-organization", headers=agent)
    assert resp.status_code == 200
    assert resp.json()["slug"] == "agent-slug-org"


async def test_it_never_leaks_another_organizations_slug(client: AsyncClient, unique_email: str):
    await _register_org(client, "Org A Widget", unique_email)
    tokens_b = await _register_org(client, "Org B Widget", f"b-{unique_email}")
    admin_b = _auth(tokens_b["access_token"])

    resp = await client.get("/api/v1/my-organization", headers=admin_b)
    assert resp.json()["slug"] == "org-b-widget"
    assert resp.json()["slug"] != "org-a-widget"
