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


def _slug(org_name: str) -> str:
    return "-".join(org_name.lower().split())


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_new_conversation_notifies_all_agents(client: AsyncClient, unique_email: str):
    org_name = f"Notif Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    admin_headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    agent_email = f"agent-{unique_email}"
    await client.post(
        "/api/v1/users",
        json={
            "email": agent_email,
            "full_name": "Agent",
            "temporary_password": "TempPass123",
            "role": "agent",
        },
        headers=admin_headers,
    )
    agent_login = await client.post(
        "/api/v1/auth/login", json={"email": agent_email, "password": "TempPass123"}
    )
    agent_headers = _auth_header(agent_login.json()["access_token"])

    await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": "v1", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
    )

    admin_notifs = await client.get("/api/v1/notifications", headers=admin_headers)
    agent_notifs = await client.get("/api/v1/notifications", headers=agent_headers)
    assert any(n["type"] == "new_conversation" for n in admin_notifs.json())
    assert any(n["type"] == "new_conversation" for n in agent_notifs.json())


async def test_unread_count_and_mark_read(client: AsyncClient, unique_email: str):
    org_name = f"Notif Count Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": "v2", "initial_message": "Hi", "full_name": "Test Visitor", "phone": "9990001111"},
    )

    count_resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert count_resp.json()["unread_count"] >= 1

    notif_id = (await client.get("/api/v1/notifications", headers=headers)).json()[0]["id"]
    mark_resp = await client.post(f"/api/v1/notifications/{notif_id}/read", headers=headers)
    assert mark_resp.status_code == 204

    unread_only = await client.get(
        "/api/v1/notifications?unread_only=true", headers=headers
    )
    assert not any(n["id"] == notif_id for n in unread_only.json())


async def test_mark_all_read(client: AsyncClient, unique_email: str):
    org_name = f"Notif All Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    await client.post(
        f"/api/v1/public/{slug}/conversations", json={"external_id": "v3", "initial_message": "A", "full_name": "Test Visitor", "phone": "9990001111"}
    )
    await client.post(
        f"/api/v1/public/{slug}/conversations", json={"external_id": "v4", "initial_message": "B", "full_name": "Test Visitor", "phone": "9990001111"}
    )

    await client.post("/api/v1/notifications/read-all", headers=headers)
    unread_resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert unread_resp.json()["unread_count"] == 0


async def test_conversation_transfer_notifies_new_assignee(client: AsyncClient, unique_email: str):
    org_name = f"Notif Transfer Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    admin_headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    agent_email = f"agent-{unique_email}"
    await client.post(
        "/api/v1/users",
        json={
            "email": agent_email,
            "full_name": "Agent",
            "temporary_password": "TempPass123",
            "role": "agent",
        },
        headers=admin_headers,
    )
    agent_login = await client.post(
        "/api/v1/auth/login", json={"email": agent_email, "password": "TempPass123"}
    )
    agent_headers = _auth_header(agent_login.json()["access_token"])
    agent_id = (await client.get("/api/v1/users", headers=admin_headers)).json()
    agent_id = next(u["id"] for u in agent_id if u["email"] == agent_email)

    conv = (
        await client.post(
            f"/api/v1/public/{slug}/conversations",
            json={"external_id": "v5", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
        )
    ).json()

    await client.patch(
        f"/api/v1/conversations/{conv['id']}",
        json={"assigned_agent_id": agent_id},
        headers=admin_headers,
    )

    agent_notifs = await client.get("/api/v1/notifications", headers=agent_headers)
    assert any(n["type"] == "conversation_transferred" for n in agent_notifs.json())


async def test_ticket_assignment_notifies_agent(client: AsyncClient, unique_email: str):
    org_name = f"Notif Ticket Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    admin_headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    agent_email = f"agent-{unique_email}"
    await client.post(
        "/api/v1/users",
        json={
            "email": agent_email,
            "full_name": "Agent",
            "temporary_password": "TempPass123",
            "role": "agent",
        },
        headers=admin_headers,
    )
    agent_login = await client.post(
        "/api/v1/auth/login", json={"email": agent_email, "password": "TempPass123"}
    )
    agent_headers = _auth_header(agent_login.json()["access_token"])
    agent_id = next(
        u["id"]
        for u in (await client.get("/api/v1/users", headers=admin_headers)).json()
        if u["email"] == agent_email
    )

    conv = (
        await client.post(
            f"/api/v1/public/{slug}/conversations",
            json={"external_id": "v6", "initial_message": "Hi", "full_name": "Test Visitor", "phone": "9990001111"},
        )
    ).json()

    await client.post(
        "/api/v1/tickets",
        json={
            "customer_id": conv["customer_id"],
            "conversation_id": conv["id"],
            "subject": "Escalation",
            "description": "desc",
            "assigned_agent_id": agent_id,
        },
        headers=admin_headers,
    )

    agent_notifs = await client.get("/api/v1/notifications", headers=agent_headers)
    assert any(n["type"] == "ticket_assigned" for n in agent_notifs.json())


async def test_notifications_isolated_by_organization(client: AsyncClient, unique_email: str):
    org_a_name = f"Notif Iso A {unique_email}"
    org_b_name = f"Notif Iso B {unique_email}"
    tokens_a = await _register_org(client, org_a_name, f"a-{unique_email}")
    tokens_b = await _register_org(client, org_b_name, f"b-{unique_email}")

    await client.post(
        f"/api/v1/public/{_slug(org_a_name)}/conversations",
        json={"external_id": "va", "initial_message": "org a", "full_name": "Test Visitor", "phone": "9990001111"},
    )

    notifs_b = await client.get("/api/v1/notifications", headers=_auth_header(tokens_b["access_token"]))
    assert notifs_b.json() == []


async def test_notifications_require_authentication(client: AsyncClient):
    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 401
