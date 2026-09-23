import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient, email: str, org_name: str = "Acme Corp") -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": org_name,
            "admin_full_name": "Jane Admin",
            "admin_email": email,
            "admin_password": "SuperSecret123",
        },
    )
    return resp


async def test_register_organization_creates_org_admin(client: AsyncClient, unique_email: str):
    resp = await _register(client, unique_email)
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_register_duplicate_email_returns_409(client: AsyncClient, unique_email: str):
    first = await _register(client, unique_email)
    assert first.status_code == 201

    second = await _register(client, unique_email, org_name="Different Org")
    assert second.status_code == 409


async def test_login_with_correct_password_succeeds(client: AsyncClient, unique_email: str):
    await _register(client, unique_email)
    resp = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "SuperSecret123"}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_with_wrong_password_returns_401(client: AsyncClient, unique_email: str):
    await _register(client, unique_email)
    resp = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "WrongPassword"}
    )
    assert resp.status_code == 401


async def test_login_with_unknown_email_returns_401(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )
    assert resp.status_code == 401


async def test_refresh_token_rotation(client: AsyncClient, unique_email: str):
    register_resp = await _register(client, unique_email)
    refresh_token = register_resp.json()["refresh_token"]

    first_refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert first_refresh.status_code == 200
    assert first_refresh.json()["refresh_token"] != refresh_token

    # Reusing the now-rotated (revoked) token must fail — proves rotation
    # actually revokes the old token rather than just issuing a new one.
    second_refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert second_refresh.status_code == 401


async def test_refresh_with_garbage_token_returns_401(client: AsyncClient):
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


async def test_create_api_key_requires_authentication(client: AsyncClient):
    resp = await client.post("/api/v1/auth/api-keys", json={"name": "No Auth Key", "scopes": []})
    assert resp.status_code == 401


async def test_org_admin_can_create_api_key(client: AsyncClient, unique_email: str):
    register_resp = await _register(client, unique_email)
    access_token = register_resp.json()["access_token"]

    resp = await client.post(
        "/api/v1/auth/api-keys",
        json={"name": "CRM Key", "scopes": ["conversations.read"]},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["api_key"].startswith("oc_live_")
    assert body["name"] == "CRM Key"


async def test_logout_revokes_refresh_token(client: AsyncClient, unique_email: str):
    register_resp = await _register(client, unique_email)
    refresh_token = register_resp.json()["refresh_token"]

    logout_resp = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_resp.status_code == 204

    reuse_resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_resp.status_code == 401
