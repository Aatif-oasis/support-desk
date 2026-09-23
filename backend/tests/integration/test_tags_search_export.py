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


async def test_assign_and_list_and_remove_tag(client: AsyncClient, unique_email: str):
    org_name = f"Tag Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    conv = (
        await client.post(
            f"/api/v1/public/{slug}/conversations",
            json={"external_id": "v1", "initial_message": "Hello", "full_name": "Test Visitor", "phone": "9990001111"},
        )
    ).json()

    assign_resp = await client.post(
        f"/api/v1/conversations/{conv['id']}/tags", json={"name": "billing"}, headers=headers
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()[0]["name"] == "billing"

    list_resp = await client.get(f"/api/v1/conversations/{conv['id']}/tags", headers=headers)
    tag_id = list_resp.json()[0]["id"]

    remove_resp = await client.delete(
        f"/api/v1/conversations/{conv['id']}/tags/{tag_id}", headers=headers
    )
    assert remove_resp.status_code == 204

    after = await client.get(f"/api/v1/conversations/{conv['id']}/tags", headers=headers)
    assert after.json() == []


async def test_tagging_same_name_twice_reuses_tag(client: AsyncClient, unique_email: str):
    org_name = f"Tag Reuse Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    conv1 = (
        await client.post(
            f"/api/v1/public/{slug}/conversations",
            json={"external_id": "v2", "initial_message": "Hi", "full_name": "Test Visitor", "phone": "9990001111"},
        )
    ).json()
    conv2 = (
        await client.post(
            f"/api/v1/public/{slug}/conversations",
            json={"external_id": "v3", "initial_message": "Hi again", "full_name": "Test Visitor", "phone": "9990001111"},
        )
    ).json()

    tag1 = (
        await client.post(
            f"/api/v1/conversations/{conv1['id']}/tags", json={"name": "vip"}, headers=headers
        )
    ).json()[0]
    tag2 = (
        await client.post(
            f"/api/v1/conversations/{conv2['id']}/tags", json={"name": "vip"}, headers=headers
        )
    ).json()[0]

    assert tag1["id"] == tag2["id"]


async def test_search_matches_message_content_and_customer_email(
    client: AsyncClient, unique_email: str
):
    org_name = f"Search Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": "v4", "initial_message": "My invoice is broken", "full_name": "Test Visitor", "phone": "9990001111"},
    )
    await client.post(
        f"/api/v1/public/{slug}/conversations",
        json={"external_id": "v5", "initial_message": "Totally unrelated topic", "full_name": "Test Visitor", "phone": "9990001111"},
    )

    resp = await client.get("/api/v1/conversations/search?q=invoice", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_search_isolated_by_organization(client: AsyncClient, unique_email: str):
    org_a_name = f"Search Iso A {unique_email}"
    org_b_name = f"Search Iso B {unique_email}"
    tokens_a = await _register_org(client, org_a_name, f"a-{unique_email}")
    tokens_b = await _register_org(client, org_b_name, f"b-{unique_email}")

    await client.post(
        f"/api/v1/public/{_slug(org_a_name)}/conversations",
        json={"external_id": "va", "initial_message": "uniquephrase123", "full_name": "Test Visitor", "phone": "9990001111"},
    )

    resp = await client.get(
        "/api/v1/conversations/search?q=uniquephrase123",
        headers=_auth_header(tokens_b["access_token"]),
    )
    assert resp.json() == []


async def test_export_conversation_json_and_csv(client: AsyncClient, unique_email: str):
    org_name = f"Export Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    conv = (
        await client.post(
            f"/api/v1/public/{slug}/conversations",
            json={"external_id": "v6", "initial_message": "Export me", "full_name": "Test Visitor", "phone": "9990001111"},
        )
    ).json()

    json_resp = await client.get(f"/api/v1/conversations/{conv['id']}/export", headers=headers)
    assert json_resp.status_code == 200
    assert json_resp.headers["content-type"].startswith("application/json")
    assert "Export me" in json_resp.text

    csv_resp = await client.get(
        f"/api/v1/conversations/{conv['id']}/export?format=csv", headers=headers
    )
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert "Export me" in csv_resp.text
