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


async def test_org_admin_can_crud_automation_rule(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Auto Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    create_resp = await client.post(
        "/api/v1/automation-rules",
        json={
            "name": "Tag urgent",
            "trigger_event": "message_received",
            "conditions": [{"field": "message_content", "operator": "contains", "value": "urgent"}],
            "actions": [{"type": "add_tag", "tag": "urgent"}],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    rule_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"/api/v1/automation-rules/{rule_id}", json={"is_active": False}, headers=headers
    )
    assert update_resp.json()["is_active"] is False

    delete_resp = await client.delete(f"/api/v1/automation-rules/{rule_id}", headers=headers)
    assert delete_resp.status_code == 204


async def test_agent_cannot_create_automation_rule(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Auto RBAC Org", unique_email)
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
        "/api/v1/automation-rules",
        json={"name": "X", "trigger_event": "message_received", "actions": []},
        headers=agent_headers,
    )
    assert resp.status_code == 403


async def test_auto_tag_rule_fires_on_conversation_created(client: AsyncClient, unique_email: str):
    org_name = f"Auto Tag Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    await client.post(
        "/api/v1/automation-rules",
        json={
            "name": "Tag refunds",
            "trigger_event": "conversation_created",
            "conditions": [{"field": "message_content", "operator": "contains", "value": "refund"}],
            "actions": [{"type": "add_tag", "tag": "refund-request"}],
        },
        headers=headers,
    )

    conv = (
        await client.post(
            f"/api/v1/public/{slug}/conversations",
            json={"external_id": "v1", "initial_message": "I need a refund please", "full_name": "Test Visitor", "phone": "9990001111"},
        )
    ).json()

    tags_resp = await client.get(f"/api/v1/conversations/{conv['id']}/tags", headers=headers)
    assert any(t["name"] == "refund-request" for t in tags_resp.json())


async def test_rule_does_not_fire_when_condition_does_not_match(
    client: AsyncClient, unique_email: str
):
    org_name = f"Auto NoMatch Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    await client.post(
        "/api/v1/automation-rules",
        json={
            "name": "Tag refunds",
            "trigger_event": "conversation_created",
            "conditions": [{"field": "message_content", "operator": "contains", "value": "refund"}],
            "actions": [{"type": "add_tag", "tag": "refund-request"}],
        },
        headers=headers,
    )

    conv = (
        await client.post(
            f"/api/v1/public/{slug}/conversations",
            json={"external_id": "v2", "initial_message": "Just saying hi", "full_name": "Test Visitor", "phone": "9990001111"},
        )
    ).json()

    tags_resp = await client.get(f"/api/v1/conversations/{conv['id']}/tags", headers=headers)
    assert tags_resp.json() == []


async def test_auto_reply_rule_sends_system_message(client: AsyncClient, unique_email: str):
    org_name = f"Auto Reply Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    await client.post(
        "/api/v1/automation-rules",
        json={
            "name": "Greeting auto-reply",
            "trigger_event": "conversation_created",
            "conditions": [],
            "actions": [{"type": "auto_reply", "content": "Thanks for reaching out, we'll be with you shortly!"}],
        },
        headers=headers,
    )

    conv = (
        await client.post(
            f"/api/v1/public/{slug}/conversations",
            json={"external_id": "v3", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
        )
    ).json()

    detail = await client.get(f"/api/v1/conversations/{conv['id']}", headers=headers)
    messages = detail.json()["messages"]

    # Assert on the reply itself rather than on a message count: opening
    # the conversation above also files a "joined the chat" line, and this
    # test is about the rule firing, not about how many lines are in the
    # thread.
    contents = [m["content"] for m in messages]
    assert "Hello" in contents
    assert "Thanks for reaching out, we'll be with you shortly!" in contents
    assert messages[1]["sender_type"] == "system"
    assert "shortly" in messages[1]["content"]


async def test_inactive_rule_does_not_fire(client: AsyncClient, unique_email: str):
    org_name = f"Auto Inactive Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    await client.post(
        "/api/v1/automation-rules",
        json={
            "name": "Disabled greeting",
            "trigger_event": "conversation_created",
            "conditions": [],
            "actions": [{"type": "auto_reply", "content": "Should not appear"}],
            "is_active": False,
        },
        headers=headers,
    )

    conv = (
        await client.post(
            f"/api/v1/public/{slug}/conversations",
            json={"external_id": "v4", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
        )
    ).json()

    detail = await client.get(f"/api/v1/conversations/{conv['id']}", headers=headers)
    # Only the visitor's own message should be here: an inactive rule adds
    # nothing. The agent greeting is filtered out because opening the chat
    # to read it is what sends that greeting.
    customer_messages = [
        m for m in detail.json()["messages"] if m["sender_type"] == "customer"
    ]
    assert len(customer_messages) == 1


async def test_automation_rules_isolated_by_organization(client: AsyncClient, unique_email: str):
    org_a_name = f"Auto Iso A {unique_email}"
    org_b_name = f"Auto Iso B {unique_email}"
    tokens_a = await _register_org(client, org_a_name, f"a-{unique_email}")
    tokens_b = await _register_org(client, org_b_name, f"b-{unique_email}")

    await client.post(
        "/api/v1/automation-rules",
        json={"name": "Org A rule", "trigger_event": "message_received", "actions": []},
        headers=_auth_header(tokens_a["access_token"]),
    )

    list_b = await client.get("/api/v1/automation-rules", headers=_auth_header(tokens_b["access_token"]))
    assert not any(r["name"] == "Org A rule" for r in list_b.json())
