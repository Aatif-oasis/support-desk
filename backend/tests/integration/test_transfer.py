"""
Reproduces the reported failure: an agent transfers a live chat to a
colleague, the interface shows the handover, but the colleague cannot
carry on the conversation.
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


def _slug(org_name: str) -> str:
    return "-".join(org_name.lower().split())


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _invite_agent(client, admin_headers, email: str, name: str) -> str:
    resp = await client.post(
        "/api/v1/users",
        json={
            "email": email,
            "full_name": name,
            "temporary_password": "AgentPass123",
            "role": "agent",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _login(client, email: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "AgentPass123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_transferred_agent_can_continue_the_conversation(client: AsyncClient, unique_email: str):
    org = "Transfer Org"
    admin_tokens = await _register_org(client, org, unique_email)
    admin_headers = _auth(admin_tokens["access_token"])
    slug = _slug(org)

    agent_a_id = await _invite_agent(client, admin_headers, "agent.a@example.com", "Agent A")
    agent_b_id = await _invite_agent(client, admin_headers, "agent.b@example.com", "Agent B")
    a_headers = _auth((await _login(client, "agent.a@example.com"))["access_token"])
    b_headers = _auth((await _login(client, "agent.b@example.com"))["access_token"])

    # A visitor starts a chat.
    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={
            "external_id": "visitor-transfer-1",
            "initial_message": "My printer is offline",
            "full_name": "Ravi Kumar",
            "phone": "+919720961443",
        },
    )
    assert start.status_code == 201, start.text
    conversation_id = start.json()["id"]

    # Agent A opens it, which claims it, and replies.
    opened = await client.get(f"/api/v1/conversations/{conversation_id}", headers=a_headers)
    assert opened.status_code == 200, opened.text
    assert opened.json()["assigned_agent_id"] == agent_a_id

    reply_a = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Let me check that for you"},
        headers=a_headers,
    )
    assert reply_a.status_code in (200, 201), reply_a.text

    # Agent A hands the chat to Agent B.
    transfer = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"assigned_agent_id": agent_b_id},
        headers=a_headers,
    )
    assert transfer.status_code == 200, transfer.text
    assert transfer.json()["assigned_agent_id"] == agent_b_id

    # The whole point of the handover: B must now be able to read it...
    b_opens = await client.get(f"/api/v1/conversations/{conversation_id}", headers=b_headers)
    assert b_opens.status_code == 200, f"B could not open the chat: {b_opens.text}"
    assert b_opens.json()["assigned_agent_id"] == agent_b_id

    # ...and carry on talking to the customer.
    reply_b = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Hi, I'm taking over from my colleague"},
        headers=b_headers,
    )
    assert reply_b.status_code in (200, 201), f"B could not reply: {reply_b.text}"

    # And A, who no longer owns it, must not be able to keep replying.
    reply_a_again = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "still me"},
        headers=a_headers,
    )
    assert reply_a_again.status_code == 403, "A should have lost access after handing it over"


async def test_agent_can_return_a_chat_to_the_queue(client: AsyncClient, unique_email: str):
    org = "Queue Org"
    admin_tokens = await _register_org(client, org, unique_email)
    admin_headers = _auth(admin_tokens["access_token"])
    slug = _slug(org)

    await _invite_agent(client, admin_headers, "agent.c@example.com", "Agent C")
    c_headers = _auth((await _login(client, "agent.c@example.com"))["access_token"])

    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={
            "external_id": "visitor-queue-1",
            "initial_message": "Hello",
            "full_name": "Sita Devi",
            "phone": "+919720961444",
        },
    )
    conversation_id = start.json()["id"]

    await client.get(f"/api/v1/conversations/{conversation_id}", headers=c_headers)

    unassign = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"assigned_agent_id": None},
        headers=c_headers,
    )
    assert unassign.status_code == 200, unassign.text
    assert unassign.json()["assigned_agent_id"] is None
