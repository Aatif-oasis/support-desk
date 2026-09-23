import hashlib
import hmac
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _start_capture_server():
    """
    A real local HTTP server (not a mock) so the test proves dispatch()
    actually performs a network call with a correctly-signed body — not
    just that it constructs the right payload in memory.
    """
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            received.append(
                {
                    "body": body,
                    "signature": self.headers.get("X-Oasis-Signature"),
                    "event": self.headers.get("X-Oasis-Event"),
                }
            )
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, received


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


async def test_webhook_subscription_crud(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Webhook Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    create_resp = await client.post(
        "/api/v1/webhooks",
        json={"url": "https://example.com/hook", "events": ["chat.created"]},
        headers=headers,
    )
    assert create_resp.status_code == 201
    assert "secret" in create_resp.json()
    sub_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/webhooks", headers=headers)
    assert any(s["id"] == sub_id for s in list_resp.json())
    assert "secret" not in list_resp.json()[0]

    delete_resp = await client.delete(f"/api/v1/webhooks/{sub_id}", headers=headers)
    assert delete_resp.status_code == 204


async def test_invalid_event_name_rejected(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Webhook Invalid Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    resp = await client.post(
        "/api/v1/webhooks",
        json={"url": "https://example.com/hook", "events": ["not.a.real.event"]},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_agent_cannot_manage_webhooks(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Webhook RBAC Org", unique_email)
    admin_headers = _auth_header(tokens["access_token"])

    agent_email = f"agent-{unique_email}"
    await client.post(
        "/api/v1/users",
        json={"email": agent_email, "full_name": "Agent", "temporary_password": "TempPass123", "role": "agent"},
        headers=admin_headers,
    )
    login = await client.post("/api/v1/auth/login", json={"email": agent_email, "password": "TempPass123"})
    agent_headers = _auth_header(login.json()["access_token"])

    resp = await client.post(
        "/api/v1/webhooks", json={"url": "https://x.com", "events": ["chat.created"]}, headers=agent_headers
    )
    assert resp.status_code == 403


async def test_chat_created_webhook_actually_delivers_with_valid_signature(
    client: AsyncClient, unique_email: str
):
    server, port, received = _start_capture_server()
    try:
        org_name = f"Webhook Live Org {unique_email}"
        tokens = await _register_org(client, org_name, unique_email)
        headers = _auth_header(tokens["access_token"])
        slug = _slug(org_name)

        create_resp = await client.post(
            "/api/v1/webhooks",
            json={"url": f"http://127.0.0.1:{port}/hook", "events": ["chat.created", "message.received"]},
            headers=headers,
        )
        secret = create_resp.json()["secret"]

        await client.post(
            f"/api/v1/public/{slug}/conversations",
            json={"external_id": "v1", "initial_message": "Hello there", "full_name": "Test Visitor", "phone": "9990001111"},
        )

        assert len(received) == 2
        events = {r["event"] for r in received}
        assert events == {"chat.created", "message.received"}

        for r in received:
            expected_sig = hmac.new(secret.encode(), r["body"], hashlib.sha256).hexdigest()
            assert r["signature"] == expected_sig
    finally:
        server.shutdown()


async def test_unsubscribed_event_is_not_delivered(client: AsyncClient, unique_email: str):
    server, port, received = _start_capture_server()
    try:
        org_name = f"Webhook Filter Org {unique_email}"
        tokens = await _register_org(client, org_name, unique_email)
        headers = _auth_header(tokens["access_token"])
        slug = _slug(org_name)

        await client.post(
            "/api/v1/webhooks",
            json={"url": f"http://127.0.0.1:{port}/hook", "events": ["ticket.created"]},
            headers=headers,
        )

        await client.post(
            f"/api/v1/public/{slug}/conversations",
            json={"external_id": "v2", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
        )

        assert len(received) == 0
    finally:
        server.shutdown()


async def test_delivery_to_unreachable_url_is_logged_not_raised(
    client: AsyncClient, unique_email: str
):
    """dispatch() must never let a broken receiver break the customer-facing request."""
    org_name = f"Webhook Broken Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    create_resp = await client.post(
        "/api/v1/webhooks",
        json={"url": "http://127.0.0.1:1/unreachable", "events": ["chat.created"]},
        headers=headers,
    )
    sub_id = create_resp.json()["id"]

    conv_resp = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": "v3", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    assert conv_resp.status_code == 201

    deliveries = await client.get(f"/api/v1/webhooks/{sub_id}/deliveries", headers=headers)
    assert len(deliveries.json()) == 1
    assert deliveries.json()[0]["error"] is not None
    assert deliveries.json()[0]["response_status"] is None
