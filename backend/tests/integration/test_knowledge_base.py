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


async def test_org_admin_can_create_category_and_article(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "KB Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    cat_resp = await client.post(
        "/api/v1/knowledge-base/categories", json={"name": "Billing"}, headers=headers
    )
    assert cat_resp.status_code == 201
    category_id = cat_resp.json()["id"]

    article_resp = await client.post(
        "/api/v1/knowledge-base/articles",
        json={"title": "How refunds work", "content": "...", "category_id": category_id, "status": "published"},
        headers=headers,
    )
    assert article_resp.status_code == 201
    assert article_resp.json()["status"] == "published"


async def test_agent_cannot_create_article(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "KB RBAC Org", unique_email)
    admin_headers = _auth_header(tokens["access_token"])

    agent_email = f"agent-{unique_email}"
    await client.post(
        "/api/v1/users",
        json={"email": agent_email, "full_name": "Agent", "temporary_password": "TempPass123", "role": "agent"},
        headers=admin_headers,
    )
    login = await client.post("/api/v1/auth/login", json={"email": agent_email, "password": "TempPass123"})
    agent_headers = _auth_header(login.json()["access_token"])

    read_resp = await client.get("/api/v1/knowledge-base/articles", headers=agent_headers)
    assert read_resp.status_code == 200

    write_resp = await client.post(
        "/api/v1/knowledge-base/articles",
        json={"title": "X", "content": "Y"},
        headers=agent_headers,
    )
    assert write_resp.status_code == 403


async def test_draft_articles_hidden_from_public_but_visible_to_agents(
    client: AsyncClient, unique_email: str
):
    org_name = f"KB Draft Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    draft_resp = await client.post(
        "/api/v1/knowledge-base/articles",
        json={"title": "Unfinished draft", "content": "wip", "status": "draft"},
        headers=headers,
    )
    article_id = draft_resp.json()["id"]

    agent_get = await client.get(f"/api/v1/knowledge-base/articles/{article_id}", headers=headers)
    assert agent_get.status_code == 200

    public_get = await client.get(f"/api/v1/public/{slug}/knowledge-base/articles/{article_id}")
    assert public_get.status_code == 404

    public_list = await client.get(f"/api/v1/public/{slug}/knowledge-base/articles")
    assert not any(a["id"] == article_id for a in public_list.json())


async def test_published_article_visible_publicly_and_searchable(
    client: AsyncClient, unique_email: str
):
    org_name = f"KB Publish Org {unique_email}"
    tokens = await _register_org(client, org_name, unique_email)
    headers = _auth_header(tokens["access_token"])
    slug = _slug(org_name)

    create_resp = await client.post(
        "/api/v1/knowledge-base/articles",
        json={"title": "Resetting your password", "content": "Go to settings...", "status": "published"},
        headers=headers,
    )
    article_id = create_resp.json()["id"]

    public_get = await client.get(f"/api/v1/public/{slug}/knowledge-base/articles/{article_id}")
    assert public_get.status_code == 200

    search_resp = await client.get(f"/api/v1/public/{slug}/knowledge-base/articles?q=password")
    assert any(a["id"] == article_id for a in search_resp.json())


async def test_kb_articles_isolated_by_organization(client: AsyncClient, unique_email: str):
    org_a_name = f"KB Iso A {unique_email}"
    org_b_name = f"KB Iso B {unique_email}"
    tokens_a = await _register_org(client, org_a_name, f"a-{unique_email}")
    await _register_org(client, org_b_name, f"b-{unique_email}")

    create_resp = await client.post(
        "/api/v1/knowledge-base/articles",
        json={"title": "Org A secret article", "content": "...", "status": "published"},
        headers=_auth_header(tokens_a["access_token"]),
    )
    article_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/public/{_slug(org_b_name)}/knowledge-base/articles/{article_id}")
    assert resp.status_code == 404


async def test_update_and_delete_article(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "KB Edit Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    create_resp = await client.post(
        "/api/v1/knowledge-base/articles",
        json={"title": "Old title", "content": "old"},
        headers=headers,
    )
    article_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"/api/v1/knowledge-base/articles/{article_id}", json={"title": "New title"}, headers=headers
    )
    assert update_resp.json()["title"] == "New title"

    delete_resp = await client.delete(f"/api/v1/knowledge-base/articles/{article_id}", headers=headers)
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/knowledge-base/articles/{article_id}", headers=headers)
    assert get_resp.status_code == 404
