"""
Read receipts, from both sides.

The behaviour that matters: after the other side opens the chat, their
"last read" timestamp must be later than the message that was waiting —
that comparison is what turns "Sent" into "Seen" in both interfaces.
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


async def test_agent_reading_marks_the_customer_message_seen(client: AsyncClient, unique_email: str):
    org = "Receipt Org"
    tokens = await _register_org(client, org, unique_email)
    headers = _auth(tokens["access_token"])
    slug = _slug(org)

    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={
            "external_id": "visitor-receipt-1",
            "initial_message": "Is anyone there?",
            "full_name": "Meera Nair",
            "phone": "+919720961445",
        },
    )
    conversation_id = start.json()["id"]

    # Nothing read yet.
    before = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert before.json()["agent_last_read_at"] is None

    read = await client.post(f"/api/v1/conversations/{conversation_id}/read", headers=headers)
    assert read.status_code == 204, read.text

    after = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert after.json()["agent_last_read_at"] is not None

    # The widget reads this field to decide "Seen".
    history = await client.get(
        f"/api/v1/public/{slug}/conversations/{conversation_id}",
        params={"external_id": "visitor-receipt-1"},
    )
    assert history.status_code == 200, history.text
    assert history.json()["agent_last_read_at"] is not None


async def test_customer_reading_marks_the_agent_reply_seen(client: AsyncClient, unique_email: str):
    org = "Receipt Two"
    tokens = await _register_org(client, org, unique_email)
    headers = _auth(tokens["access_token"])
    slug = _slug(org)

    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={
            "external_id": "visitor-receipt-2",
            "initial_message": "Hello",
            "full_name": "Arun Rao",
            "phone": "+919720961446",
        },
    )
    conversation_id = start.json()["id"]

    await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Hi Arun, how can I help?"},
        headers=headers,
    )

    detail = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert detail.json()["customer_last_read_at"] is None

    read = await client.post(
        f"/api/v1/public/{slug}/conversations/{conversation_id}/read",
        params={"external_id": "visitor-receipt-2"},
    )
    assert read.status_code == 204, read.text

    after = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert after.json()["customer_last_read_at"] is not None


async def test_a_stranger_cannot_mark_someone_elses_chat_read(client: AsyncClient, unique_email: str):
    """A receipt is a write, so it needs the same ownership check as reading."""
    org = "Receipt Three"
    tokens = await _register_org(client, org, unique_email)
    headers = _auth(tokens["access_token"])
    slug = _slug(org)

    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={
            "external_id": "visitor-receipt-3",
            "initial_message": "Hello",
            "full_name": "Sunil Das",
            "phone": "+919720961447",
        },
    )
    conversation_id = start.json()["id"]
    await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)

    resp = await client.post(
        f"/api/v1/public/{slug}/conversations/{conversation_id}/read",
        params={"external_id": "some-other-visitor"},
    )
    assert resp.status_code == 403, resp.text
