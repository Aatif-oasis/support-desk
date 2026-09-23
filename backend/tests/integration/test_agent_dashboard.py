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


# ---------- Quick Replies ----------

async def test_org_admin_can_create_and_list_quick_replies(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "QR Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    create_resp = await client.post(
        "/api/v1/quick-replies",
        json={"title": "Greeting", "content": "Hi! How can I help you today?"},
        headers=headers,
    )
    assert create_resp.status_code == 201

    list_resp = await client.get("/api/v1/quick-replies", headers=headers)
    assert list_resp.status_code == 200
    assert any(qr["title"] == "Greeting" for qr in list_resp.json())


async def test_agent_can_read_but_not_create_quick_replies(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "QR RBAC Org", unique_email)
    admin_headers = _auth_header(tokens["access_token"])

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

    read_resp = await client.get("/api/v1/quick-replies", headers=agent_headers)
    assert read_resp.status_code == 200

    write_resp = await client.post(
        "/api/v1/quick-replies", json={"title": "X", "content": "Y"}, headers=agent_headers
    )
    assert write_resp.status_code == 403


async def test_quick_reply_update_and_delete(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "QR Edit Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    create_resp = await client.post(
        "/api/v1/quick-replies", json={"title": "Old", "content": "Old text"}, headers=headers
    )
    qr_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"/api/v1/quick-replies/{qr_id}", json={"title": "New"}, headers=headers
    )
    assert update_resp.json()["title"] == "New"
    assert update_resp.json()["content"] == "Old text"

    delete_resp = await client.delete(f"/api/v1/quick-replies/{qr_id}", headers=headers)
    assert delete_resp.status_code == 204

    list_resp = await client.get("/api/v1/quick-replies", headers=headers)
    assert not any(qr["id"] == qr_id for qr in list_resp.json())


async def test_quick_replies_isolated_by_organization(client: AsyncClient, unique_email: str):
    tokens_a = await _register_org(client, "QR Iso A", f"a-{unique_email}")
    tokens_b = await _register_org(client, "QR Iso B", f"b-{unique_email}")

    await client.post(
        "/api/v1/quick-replies",
        json={"title": "A's reply", "content": "..."},
        headers=_auth_header(tokens_a["access_token"]),
    )

    list_b = await client.get("/api/v1/quick-replies", headers=_auth_header(tokens_b["access_token"]))
    assert not any(qr["title"] == "A's reply" for qr in list_b.json())


# ---------- Conversation Notes ----------

async def test_agent_can_add_and_list_conversation_notes(client: AsyncClient, unique_email: str):
    org_name = f"Notes Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])

    start = await client.post(
        f"/api/v1/public/{_slug(org_name)}/conversations",
        json={"external_id": "visitor-notes", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    conversation_id = start.json()["id"]

    note_resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/notes",
        json={"text": "Escalate to billing team"},
        headers=headers,
    )
    assert note_resp.status_code == 201
    assert note_resp.json()["text"] == "Escalate to billing team"

    list_resp = await client.get(f"/api/v1/conversations/{conversation_id}/notes", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_conversation_notes_never_appear_in_customer_message_list(
    client: AsyncClient, unique_email: str
):
    """
    The whole point of internal notes: they must never leak into the
    message thread a customer's widget can see.
    """
    org_name = f"Notes Leak Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": "visitor-leak", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    conversation_id = start.json()["id"]

    await client.post(
        f"/api/v1/conversations/{conversation_id}/notes",
        json={"text": "Secret internal note — do not leak"},
        headers=headers,
    )

    detail = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    message_contents = [m["content"] for m in detail.json()["messages"]]
    assert "Secret internal note — do not leak" not in message_contents


async def test_conversation_notes_require_authentication(client: AsyncClient, unique_email: str):
    org_name = f"Notes Auth Org {unique_email}"
    await _register_org(client, org_name, unique_email)
    slug = _slug(org_name)

    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": "v", "initial_message": "Hi", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    conversation_id = start.json()["id"]

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/notes", json={"text": "nope"}
    )
    assert resp.status_code == 401
