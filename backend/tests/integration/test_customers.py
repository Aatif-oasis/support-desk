import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _expected_slug(org_name: str) -> str:
    return "-".join(org_name.lower().split())


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


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_identify_creates_new_customer(client: AsyncClient, unique_email: str):
    await _register_org(client, "Identify Org", unique_email)

    resp = await client.post(
        "/api/v1/public/identify-org/customers/identify",
        json={"external_id": "visitor-1", "browser": "Firefox"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["external_id"] == "visitor-1"
    assert body["email"] is None


async def test_identify_is_idempotent_and_progressively_enriches(
    client: AsyncClient, unique_email: str
):
    await _register_org(client, "Enrich Org", unique_email)

    first = await client.post(
        "/api/v1/public/enrich-org/customers/identify",
        json={"external_id": "visitor-2", "browser": "Safari"},
    )
    customer_id = first.json()["id"]

    second = await client.post(
        "/api/v1/public/enrich-org/customers/identify",
        json={"external_id": "visitor-2", "email": "later@example.com", "full_name": "Later Name"},
    )
    assert second.json()["id"] == customer_id  # same row, not a duplicate
    assert second.json()["email"] == "later@example.com"
    assert second.json()["full_name"] == "Later Name"


async def test_identify_unknown_org_slug_returns_404(client: AsyncClient):
    resp = await client.post(
        "/api/v1/public/no-such-org/customers/identify", json={"external_id": "x"}
    )
    assert resp.status_code == 404


async def test_customers_are_isolated_by_organization(client: AsyncClient, unique_email: str):
    """
    The most important test in this module: two orgs both use external_id
    'shared-id' (plausible — widget IDs aren't globally coordinated). They
    must resolve to two completely separate Customer rows, and neither
    org's agents can see the other's customer data.
    """
    org_a_email = f"a-{unique_email}"
    org_b_email = f"b-{unique_email}"
    tokens_a = await _register_org(client, "Org A", org_a_email)
    tokens_b = await _register_org(client, "Org B", org_b_email)

    await client.post(
        "/api/v1/public/org-a/customers/identify",
        json={"external_id": "shared-id", "full_name": "Org A's Customer"},
    )
    await client.post(
        "/api/v1/public/org-b/customers/identify",
        json={"external_id": "shared-id", "full_name": "Org B's Customer"},
    )

    list_a = await client.get("/api/v1/customers", headers=_auth_header(tokens_a["access_token"]))
    list_b = await client.get("/api/v1/customers", headers=_auth_header(tokens_b["access_token"]))

    names_a = [c["full_name"] for c in list_a.json()]
    names_b = [c["full_name"] for c in list_b.json()]

    assert "Org A's Customer" in names_a
    assert "Org B's Customer" not in names_a
    assert "Org B's Customer" in names_b
    assert "Org A's Customer" not in names_b


async def test_org_a_cannot_fetch_org_b_customer_by_id(client: AsyncClient, unique_email: str):
    org_a_email = f"a2-{unique_email}"
    org_b_email = f"b2-{unique_email}"
    tokens_a = await _register_org(client, "Org A2", org_a_email)
    tokens_b = await _register_org(client, "Org B2", org_b_email)

    identify_resp = await client.post(
        "/api/v1/public/org-b2/customers/identify", json={"external_id": "victim"}
    )
    org_b_customer_id = identify_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/customers/{org_b_customer_id}", headers=_auth_header(tokens_a["access_token"])
    )
    assert resp.status_code == 404


async def test_agent_can_view_and_note_customers(client: AsyncClient, unique_email: str):
    tokens = await _register_org(client, "Note Org", unique_email)
    headers = _auth_header(tokens["access_token"])

    identify_resp = await client.post(
        "/api/v1/public/note-org/customers/identify", json={"external_id": "notee"}
    )
    customer_id = identify_resp.json()["id"]

    note_resp = await client.post(
        f"/api/v1/customers/{customer_id}/notes", json={"text": "Interested in Pro plan"}, headers=headers
    )
    assert note_resp.status_code == 200
    assert note_resp.json()["notes"][0]["text"] == "Interested in Pro plan"

    tag_resp = await client.patch(
        f"/api/v1/customers/{customer_id}", json={"tags": ["warm-lead"]}, headers=headers
    )
    assert tag_resp.json()["tags"] == ["warm-lead"]


async def test_customer_endpoints_require_authentication(client: AsyncClient):
    resp = await client.get("/api/v1/customers")
    assert resp.status_code == 401
