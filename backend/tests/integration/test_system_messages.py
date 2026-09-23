"""
System announcements in the thread.

These lines are the difference between a visitor watching a silent screen
and knowing a named person picked up their chat. They are stored as
messages so both sides see them live and still see them after a refresh.
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _register_org(client: AsyncClient, org_name: str, email: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": org_name,
            "admin_full_name": "Anita Admin",
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
        json={"email": email, "full_name": name, "temporary_password": "AgentPass123", "role": "agent"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _login(client, email: str) -> dict:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "AgentPass123"})
    return resp.json()


async def _start_chat(client, slug: str, external_id: str) -> str:
    resp = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={
            "external_id": external_id,
            "initial_message": "Hello, is anyone there?",
            "full_name": "Neha Gupta",
            "phone": "+919720961455",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _system_lines(messages: list[dict]) -> list[str]:
    return [m["content"] for m in messages if m["sender_type"] == "system"]


async def test_visitor_gets_a_greeting_from_the_agent_who_picks_up(
    client: AsyncClient, unique_email: str
):
    org = "Join Org"
    admin = await _register_org(client, org, unique_email)
    admin_headers = _auth(admin["access_token"])
    slug = _slug(org)

    await _invite_agent(client, admin_headers, "rahul@example.com", "Rahul Verma")
    rahul = _auth((await _login(client, "rahul@example.com"))["access_token"])

    conversation_id = await _start_chat(client, slug, "visitor-join-1")
    await client.get(f"/api/v1/conversations/{conversation_id}", headers=rahul)

    # The widget reads exactly this endpoint, so assert against it.
    history = await client.get(
        f"/api/v1/public/{slug}/conversations/{conversation_id}",
        params={"external_id": "visitor-join-1"},
    )
    messages = history.json()["messages"]

    # The greeting arrives as the agent speaking, so it carries their name
    # and their sender id — not as a neutral system notice.
    greeting = [m for m in messages if m["sender_type"] == "agent"]
    assert len(greeting) == 1, messages
    assert "Rahul Verma" in greeting[0]["content"]
    assert greeting[0]["sender_id"] is not None


async def test_transfer_is_announced_with_both_names(client: AsyncClient, unique_email: str):
    org = "Handover Org"
    admin = await _register_org(client, org, unique_email)
    admin_headers = _auth(admin["access_token"])
    slug = _slug(org)

    await _invite_agent(client, admin_headers, "rahul2@example.com", "Rahul Verma")
    priya_id = await _invite_agent(client, admin_headers, "priya@example.com", "Priya Nair")
    rahul = _auth((await _login(client, "rahul2@example.com"))["access_token"])

    conversation_id = await _start_chat(client, slug, "visitor-join-2")
    await client.get(f"/api/v1/conversations/{conversation_id}", headers=rahul)

    transfer = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"assigned_agent_id": priya_id},
        headers=rahul,
    )
    assert transfer.status_code == 200, transfer.text

    history = await client.get(
        f"/api/v1/public/{slug}/conversations/{conversation_id}",
        params={"external_id": "visitor-join-2"},
    )
    # The handover is a system line: nobody said it, it just happened.
    lines = _system_lines(history.json()["messages"])
    assert lines == ["Rahul Verma transferred this chat to Priya Nair"], lines


async def test_returning_a_chat_to_the_queue_is_announced(client: AsyncClient, unique_email: str):
    org = "Queue Back Org"
    admin = await _register_org(client, org, unique_email)
    admin_headers = _auth(admin["access_token"])
    slug = _slug(org)

    await _invite_agent(client, admin_headers, "sam@example.com", "Sameer Khan")
    sam = _auth((await _login(client, "sam@example.com"))["access_token"])

    conversation_id = await _start_chat(client, slug, "visitor-join-3")
    await client.get(f"/api/v1/conversations/{conversation_id}", headers=sam)
    await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"assigned_agent_id": None},
        headers=sam,
    )

    history = await client.get(
        f"/api/v1/public/{slug}/conversations/{conversation_id}",
        params={"external_id": "visitor-join-3"},
    )
    assert "This chat was returned to the queue" in _system_lines(history.json()["messages"])


async def test_a_supervisor_looking_in_is_not_written_into_the_thread(
    client: AsyncClient, unique_email: str
):
    """
    The agent gets told over the socket; the visitor must never see that
    an administrator is watching their conversation.
    """
    org = "Watch Org"
    admin = await _register_org(client, org, unique_email)
    admin_headers = _auth(admin["access_token"])
    slug = _slug(org)

    await _invite_agent(client, admin_headers, "dev@example.com", "Dev Sharma")
    dev = _auth((await _login(client, "dev@example.com"))["access_token"])

    conversation_id = await _start_chat(client, slug, "visitor-join-4")
    await client.get(f"/api/v1/conversations/{conversation_id}", headers=dev)

    # Admin opens the same chat.
    opened = await client.get(f"/api/v1/conversations/{conversation_id}", headers=admin_headers)
    assert opened.status_code == 200, opened.text

    history = await client.get(
        f"/api/v1/public/{slug}/conversations/{conversation_id}",
        params={"external_id": "visitor-join-4"},
    )
    lines = _system_lines(history.json()["messages"])
    assert not any("Anita" in line or "viewing" in line for line in lines), lines
