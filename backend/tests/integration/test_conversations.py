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


async def test_start_conversation_creates_conversation_and_first_message(
    client: AsyncClient, unique_email: str
):
    org_name = f"Conv Org {unique_email}"
    await _register_org(client, org_name, unique_email)

    resp = await client.post(
        f"/api/v1/public/{_slug(org_name)}/conversations",
        json={"external_id": "visitor-1", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "open"
    assert len(body["messages"]) == 1
    assert body["messages"][0]["content"] == "Hello"
    assert body["messages"][0]["sender_type"] == "customer"


async def test_customer_can_send_followup_message(client: AsyncClient, unique_email: str):
    org_name = f"Followup Org {unique_email}"
    await _register_org(client, org_name, unique_email)
    slug = _slug(org_name)

    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": "visitor-2", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    conversation_id = start.json()["id"]

    followup = await client.post(
        f"/api/v1/public/{slug}/conversations/{conversation_id}/messages",
        json={"external_id": "visitor-2", "content": "Are you there?"},
    )
    assert followup.status_code == 200
    assert followup.json()["content"] == "Are you there?"


async def test_wrong_customer_cannot_message_someone_elses_conversation(
    client: AsyncClient, unique_email: str
):
    org_name = f"Spoof Org {unique_email}"
    await _register_org(client, org_name, unique_email)
    slug = _slug(org_name)

    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": "real-visitor", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    conversation_id = start.json()["id"]

    spoof = await client.post(
        f"/api/v1/public/{slug}/conversations/{conversation_id}/messages",
        json={"external_id": "attacker-visitor", "content": "gotcha"},
    )
    assert spoof.status_code == 403


async def test_agent_can_list_and_reply_to_conversation(client: AsyncClient, unique_email: str):
    org_name = f"Agent Reply Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": "visitor-3", "initial_message": "Need help", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    conversation_id = start.json()["id"]

    list_resp = await client.get("/api/v1/conversations", headers=headers)
    assert list_resp.status_code == 200
    assert any(c["id"] == conversation_id for c in list_resp.json())

    reply_resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "On it!"},
        headers=headers,
    )
    assert reply_resp.status_code == 200
    assert reply_resp.json()["sender_type"] == "agent"

    detail_resp = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    # The thread also carries the automatic greeting sent when the agent
    # picked the chat up, so assert on what was actually said rather than
    # on how many lines are in it.
    messages = detail_resp.json()["messages"]
    contents = [m["content"] for m in messages]
    assert "Need help" in contents          # the visitor's opening message
    assert "On it!" in contents             # the agent's typed reply


async def test_agent_cannot_modify_conversation_assigned_to_another_agent(
    client: AsyncClient, unique_email: str
):
    org_name = f"Assign Org {unique_email}"
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

    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": "visitor-4", "initial_message": "Hi", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    conversation_id = start.json()["id"]

    users_list = (await client.get("/api/v1/users", headers=admin_headers)).json()
    agent1_id = next(u["id"] for u in users_list if u["email"] == agent1_email)

    # Assign to agent1 (org_admin can assign)
    assign_resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"assigned_agent_id": agent1_id},
        headers=admin_headers,
    )
    assert assign_resp.status_code == 200

    # agent2 (not assigned) tries to close it — should be forbidden
    forbidden_resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"status": "closed"},
        headers=agent2_headers,
    )
    assert forbidden_resp.status_code == 403

    # agent1 (assigned) CAN close it
    allowed_resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"status": "closed"},
        headers=agent1_headers,
    )
    assert allowed_resp.status_code == 200
    assert allowed_resp.json()["status"] == "closed"


async def test_conversations_are_isolated_by_organization(client: AsyncClient, unique_email: str):
    org_a_name = f"ConvIso A {unique_email}"
    org_b_name = f"ConvIso B {unique_email}"
    tokens_a = await _register_org(client, org_a_name, f"a-{unique_email}")
    tokens_b = await _register_org(client, org_b_name, f"b-{unique_email}")

    start_a = await client.post(
        f"/api/v1/public/{_slug(org_a_name)}/conversations",
        json={"external_id": "v", "initial_message": "org a message", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    conversation_a_id = start_a.json()["id"]

    resp = await client.get(
        f"/api/v1/conversations/{conversation_a_id}", headers=_auth_header(tokens_b["access_token"])
    )
    assert resp.status_code == 404
