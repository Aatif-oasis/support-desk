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


def _slug(org_name: str) -> str:
    return "-".join(org_name.lower().split())


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _start_conversation(client: AsyncClient, slug: str, external_id: str = "visitor-t"):
    resp = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": external_id, "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    return resp.json()


async def test_agent_can_create_ticket_from_conversation(client: AsyncClient, unique_email: str):
    org_name = f"Ticket Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    conversation = await _start_conversation(client, slug)

    create_resp = await client.post(
        "/api/v1/tickets",
        json={
            "customer_id": conversation["customer_id"],
            "conversation_id": conversation["id"],
            "subject": "Billing issue",
            "description": "Customer was charged twice",
            "priority": "high",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["status"] == "open"
    assert body["priority"] == "high"
    assert body["conversation_id"] == conversation["id"]


async def test_ticket_create_rejects_customer_from_another_org(
    client: AsyncClient, unique_email: str
):
    org_a_name = f"Ticket Org A {unique_email}"
    org_b_name = f"Ticket Org B {unique_email}"
    tokens_a = await _register_org(client, org_a_name, f"a-{unique_email}")
    await _register_org(client, org_b_name, f"b-{unique_email}")

    conversation_b = await _start_conversation(client, _slug(org_b_name), "visitor-b")

    resp = await client.post(
        "/api/v1/tickets",
        json={
            "customer_id": conversation_b["customer_id"],
            "subject": "Should fail",
            "description": "Cross-tenant attempt",
        },
        headers=_auth_header(tokens_a["access_token"]),
    )
    assert resp.status_code == 404


async def test_ticket_list_and_filter_by_status(client: AsyncClient, unique_email: str):
    org_name = f"Ticket Filter Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    conversation = await _start_conversation(client, slug)
    create_resp = await client.post(
        "/api/v1/tickets",
        json={
            "customer_id": conversation["customer_id"],
            "conversation_id": conversation["id"],
            "subject": "Test ticket",
            "description": "desc",
        },
        headers=headers,
    )
    ticket_id = create_resp.json()["id"]

    open_list = await client.get("/api/v1/tickets?status=open", headers=headers)
    assert any(t["id"] == ticket_id for t in open_list.json())

    closed_list = await client.get("/api/v1/tickets?status=closed", headers=headers)
    assert not any(t["id"] == ticket_id for t in closed_list.json())


async def test_ticket_resolve_sets_resolved_at_and_reopen_clears_it(
    client: AsyncClient, unique_email: str
):
    org_name = f"Ticket Resolve Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    conversation = await _start_conversation(client, slug)
    create_resp = await client.post(
        "/api/v1/tickets",
        json={
            "customer_id": conversation["customer_id"],
            "conversation_id": conversation["id"],
            "subject": "Resolve me",
            "description": "desc",
        },
        headers=headers,
    )
    ticket_id = create_resp.json()["id"]

    resolve_resp = await client.patch(
        f"/api/v1/tickets/{ticket_id}", json={"status": "resolved"}, headers=headers
    )
    assert resolve_resp.json()["resolved_at"] is not None

    reopen_resp = await client.patch(
        f"/api/v1/tickets/{ticket_id}", json={"status": "open"}, headers=headers
    )
    assert reopen_resp.json()["resolved_at"] is None


async def test_agent_cannot_modify_ticket_assigned_to_another_agent(
    client: AsyncClient, unique_email: str
):
    org_name = f"Ticket Owner Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    admin_headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    agent1_email = f"agent1-{unique_email}"
    agent2_email = f"agent2-{unique_email}"
    for email in (agent1_email, agent2_email):
        await client.post(
            "/api/v1/users",
            json={
                "email": email,
                "full_name": "Agent",
                "temporary_password": "TempPass123",
                "role": "agent",
            },
            headers=admin_headers,
        )
    agent1_login = await client.post(
        "/api/v1/auth/login", json={"email": agent1_email, "password": "TempPass123"}
    )
    agent1_headers = _auth_header(agent1_login.json()["access_token"])
    agent2_login = await client.post(
        "/api/v1/auth/login", json={"email": agent2_email, "password": "TempPass123"}
    )
    agent2_headers = _auth_header(agent2_login.json()["access_token"])

    users_list = (await client.get("/api/v1/users", headers=admin_headers)).json()
    agent1_id = next(u["id"] for u in users_list if u["email"] == agent1_email)

    conversation = await _start_conversation(client, slug)
    create_resp = await client.post(
        "/api/v1/tickets",
        json={
            "customer_id": conversation["customer_id"],
            "conversation_id": conversation["id"],
            "subject": "Assigned ticket",
            "description": "desc",
            "assigned_agent_id": agent1_id,
        },
        headers=admin_headers,
    )
    ticket_id = create_resp.json()["id"]

    forbidden_resp = await client.patch(
        f"/api/v1/tickets/{ticket_id}", json={"status": "closed"}, headers=agent2_headers
    )
    assert forbidden_resp.status_code == 403

    allowed_resp = await client.patch(
        f"/api/v1/tickets/{ticket_id}", json={"status": "closed"}, headers=agent1_headers
    )
    assert allowed_resp.status_code == 200


async def test_ticket_comments_are_agent_only_and_ordered(client: AsyncClient, unique_email: str):
    org_name = f"Ticket Comment Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    conversation = await _start_conversation(client, slug)
    create_resp = await client.post(
        "/api/v1/tickets",
        json={
            "customer_id": conversation["customer_id"],
            "conversation_id": conversation["id"],
            "subject": "Comment ticket",
            "description": "desc",
        },
        headers=headers,
    )
    ticket_id = create_resp.json()["id"]

    await client.post(
        f"/api/v1/tickets/{ticket_id}/comments", json={"text": "First"}, headers=headers
    )
    await client.post(
        f"/api/v1/tickets/{ticket_id}/comments", json={"text": "Second"}, headers=headers
    )

    list_resp = await client.get(f"/api/v1/tickets/{ticket_id}/comments", headers=headers)
    texts = [c["text"] for c in list_resp.json()]
    assert texts == ["First", "Second"]

    no_auth_resp = await client.post(
        f"/api/v1/tickets/{ticket_id}/comments", json={"text": "nope"}
    )
    assert no_auth_resp.status_code == 401


async def test_tickets_are_isolated_by_organization(client: AsyncClient, unique_email: str):
    org_a_name = f"Ticket Iso A {unique_email}"
    org_b_name = f"Ticket Iso B {unique_email}"
    tokens_a = await _register_org(client, org_a_name, f"a2-{unique_email}")
    tokens_b = await _register_org(client, org_b_name, f"b2-{unique_email}")

    conversation_a = await _start_conversation(client, _slug(org_a_name), "visitor-a2")
    create_resp = await client.post(
        "/api/v1/tickets",
        json={
            "customer_id": conversation_a["customer_id"],
            "conversation_id": conversation_a["id"],
            "subject": "Org A ticket",
            "description": "desc",
        },
        headers=_auth_header(tokens_a["access_token"]),
    )
    ticket_a_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/tickets/{ticket_a_id}", headers=_auth_header(tokens_b["access_token"])
    )
    assert resp.status_code == 404
