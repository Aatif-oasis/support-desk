import io

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _slug(org_name: str) -> str:
    return "-".join(org_name.lower().split())


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register_org_and_start_conversation(client: AsyncClient, org_name: str, email: str):
    tokens_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": org_name,
            "admin_full_name": "Admin",
            "admin_email": email,
            "admin_password": "SuperSecret123",
        },
    )
    tokens = tokens_resp.json()
    slug = _slug(org_name)

    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": "visitor-1", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    conversation_id = start.json()["id"]
    return tokens, slug, conversation_id


async def test_customer_can_upload_and_download_attachment(client: AsyncClient, unique_email: str):
    org_name = f"Attach Org {unique_email}"
    tokens, slug, conversation_id = await _register_org_and_start_conversation(
        client, org_name, unique_email
    )

    file_bytes = b"fake-image-bytes-1234567890"
    upload_resp = await client.post(
        f"/api/v1/public/{slug}/conversations/{conversation_id}/attachments",
        data={"external_id": "visitor-1"},
        files={"file": ("photo.png", io.BytesIO(file_bytes), "image/png")},
    )
    assert upload_resp.status_code == 200
    attachment_id = upload_resp.json()["id"]
    assert upload_resp.json()["original_filename"] == "photo.png"

    download_resp = await client.get(
        f"/api/v1/public/{slug}/conversations/attachments/{attachment_id}/download",
        params={"external_id": "visitor-1"},
    )
    assert download_resp.status_code == 200
    assert download_resp.content == file_bytes


async def test_wrong_customer_cannot_download_attachment(client: AsyncClient, unique_email: str):
    org_name = f"AttachSpoof Org {unique_email}"
    tokens, slug, conversation_id = await _register_org_and_start_conversation(
        client, org_name, unique_email
    )

    upload_resp = await client.post(
        f"/api/v1/public/{slug}/conversations/{conversation_id}/attachments",
        data={"external_id": "visitor-1"},
        files={"file": ("secret.png", io.BytesIO(b"secret-bytes"), "image/png")},
    )
    attachment_id = upload_resp.json()["id"]

    download_resp = await client.get(
        f"/api/v1/public/{slug}/conversations/attachments/{attachment_id}/download",
        params={"external_id": "attacker-visitor"},
    )
    assert download_resp.status_code == 403


async def test_agent_can_upload_and_download_and_customer_conversation_shows_it(
    client: AsyncClient, unique_email: str
):
    org_name = f"AttachAgent Org {unique_email}"
    tokens, slug, conversation_id = await _register_org_and_start_conversation(
        client, org_name, unique_email
    )
    headers = _auth_header(tokens["access_token"])

    upload_resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/attachments",
        files={"file": ("reply.pdf", io.BytesIO(b"pdf-bytes-here"), "application/pdf")},
        headers=headers,
    )
    assert upload_resp.status_code == 200
    attachment_id = upload_resp.json()["id"]

    download_resp = await client.get(
        f"/api/v1/conversations/attachments/{attachment_id}/download", headers=headers
    )
    assert download_resp.status_code == 200
    assert download_resp.content == b"pdf-bytes-here"

    detail = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    contents = [m["content"] for m in detail.json()["messages"]]
    assert any("reply.pdf" in c for c in contents)


async def test_agent_attachment_upload_requires_authentication(client: AsyncClient, unique_email: str):
    org_name = f"AttachAuth Org {unique_email}"
    tokens, slug, conversation_id = await _register_org_and_start_conversation(
        client, org_name, unique_email
    )

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/attachments",
        files={"file": ("x.png", io.BytesIO(b"bytes"), "image/png")},
    )
    assert resp.status_code == 401


async def test_empty_file_upload_is_rejected(client: AsyncClient, unique_email: str):
    org_name = f"AttachEmpty Org {unique_email}"
    tokens, slug, conversation_id = await _register_org_and_start_conversation(
        client, org_name, unique_email
    )

    resp = await client.post(
        f"/api/v1/public/{slug}/conversations/{conversation_id}/attachments",
        data={"external_id": "visitor-1"},
        files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
    )
    assert resp.status_code == 422
