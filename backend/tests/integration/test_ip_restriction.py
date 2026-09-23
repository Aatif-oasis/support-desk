"""
Office lock: an agent pinned to an address can only work from there.

The cases that matter most are the ones where this could go wrong in a
way nobody notices until a Monday morning: an admin locking themselves
out, an untouched account suddenly refusing to work, or a token that keeps
working from anywhere once it has been issued.
"""
import pytest
from httpx import AsyncClient

from app.core.config import settings

pytestmark = pytest.mark.asyncio

OFFICE = "203.0.113.10"
ELSEWHERE = "198.51.100.77"


@pytest.fixture(autouse=True)
def trust_forwarded_header():
    """
    The test client has no real socket address, so the address is supplied
    the way nginx supplies it in production.
    """
    settings.TRUST_FORWARDED_FOR = True
    yield
    settings.TRUST_FORWARDED_FOR = False


def _from(address: str, **headers) -> dict:
    return {"X-Forwarded-For": address, **headers}


async def _register_org(client: AsyncClient, org_name: str, email: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": org_name,
            "admin_full_name": "Anita Admin",
            "admin_email": email,
            "admin_password": "SuperSecret123",
        },
        headers=_from(OFFICE),
    )
    return resp.json()


def _auth(token: str, address: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Forwarded-For": address}


async def _invite_agent(client, admin_headers, email: str) -> str:
    resp = await client.post(
        "/api/v1/users",
        json={
            "email": email,
            "full_name": "Ravi Agent",
            "temporary_password": "AgentPass123",
            "role": "agent",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _login(client, email: str, address: str):
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "AgentPass123"},
        headers=_from(address),
    )


async def test_agent_with_no_restriction_can_sign_in_from_anywhere(
    client: AsyncClient, unique_email: str
):
    """The default has to be open, or shipping this would lock out everyone."""
    tokens = await _register_org(client, "Open Org", unique_email)
    admin = _auth(tokens["access_token"], OFFICE)
    await _invite_agent(client, admin, "open.agent@example.com")

    resp = await _login(client, "open.agent@example.com", ELSEWHERE)
    assert resp.status_code == 200, resp.text


async def test_pinned_agent_is_refused_from_another_address(
    client: AsyncClient, unique_email: str
):
    tokens = await _register_org(client, "Pinned Org", unique_email)
    admin = _auth(tokens["access_token"], OFFICE)
    agent_id = await _invite_agent(client, admin, "pinned.agent@example.com")

    pin = await client.post(
        f"/api/v1/users/{agent_id}/ip-restriction",
        json={"allowed_ip": OFFICE},
        headers=admin,
    )
    assert pin.status_code == 200, pin.text

    from_office = await _login(client, "pinned.agent@example.com", OFFICE)
    assert from_office.status_code == 200, from_office.text

    from_home = await _login(client, "pinned.agent@example.com", ELSEWHERE)
    assert from_home.status_code == 403, from_home.text
    assert "approved location" in from_home.text


async def test_the_blocked_attempt_is_recorded_for_the_admin(
    client: AsyncClient, unique_email: str
):
    tokens = await _register_org(client, "Record Org", unique_email)
    admin = _auth(tokens["access_token"], OFFICE)
    agent_id = await _invite_agent(client, admin, "record.agent@example.com")
    await client.post(
        f"/api/v1/users/{agent_id}/ip-restriction", json={"allowed_ip": OFFICE}, headers=admin
    )

    await _login(client, "record.agent@example.com", ELSEWHERE)

    users = await client.get("/api/v1/users", headers=admin)
    agent = next(u for u in users.json() if u["id"] == agent_id)
    assert agent["last_blocked_ip"] == ELSEWHERE
    assert agent["last_blocked_at"] is not None


async def test_a_token_stops_working_away_from_the_office(
    client: AsyncClient, unique_email: str
):
    """
    Signing in at the office and carrying the laptop home must not keep
    working — otherwise the restriction only delays the problem.
    """
    tokens = await _register_org(client, "Carry Org", unique_email)
    admin = _auth(tokens["access_token"], OFFICE)
    agent_id = await _invite_agent(client, admin, "carry.agent@example.com")
    await client.post(
        f"/api/v1/users/{agent_id}/ip-restriction", json={"allowed_ip": OFFICE}, headers=admin
    )

    agent_tokens = (await _login(client, "carry.agent@example.com", OFFICE)).json()

    at_office = await client.get(
        "/api/v1/conversations", headers=_auth(agent_tokens["access_token"], OFFICE)
    )
    assert at_office.status_code == 200

    at_home = await client.get(
        "/api/v1/conversations", headers=_auth(agent_tokens["access_token"], ELSEWHERE)
    )
    assert at_home.status_code == 403, at_home.text


async def test_an_admin_is_never_locked_out(client: AsyncClient, unique_email: str):
    """
    Only an admin can lift a restriction, so an admin who could be locked
    out by one would leave nobody able to undo it.
    """
    tokens = await _register_org(client, "Admin Free Org", unique_email)
    admin_id = (
        await client.get("/api/v1/users", headers=_auth(tokens["access_token"], OFFICE))
    ).json()[0]["id"]

    await client.post(
        f"/api/v1/users/{admin_id}/ip-restriction",
        json={"allowed_ip": OFFICE},
        headers=_auth(tokens["access_token"], OFFICE),
    )

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "SuperSecret123"},
        headers=_from(ELSEWHERE),
    )
    assert resp.status_code == 200, resp.text


async def test_clearing_the_restriction_lets_the_agent_work_from_home(
    client: AsyncClient, unique_email: str
):
    tokens = await _register_org(client, "Unpin Org", unique_email)
    admin = _auth(tokens["access_token"], OFFICE)
    agent_id = await _invite_agent(client, admin, "unpin.agent@example.com")

    await client.post(
        f"/api/v1/users/{agent_id}/ip-restriction", json={"allowed_ip": OFFICE}, headers=admin
    )
    assert (await _login(client, "unpin.agent@example.com", ELSEWHERE)).status_code == 403

    cleared = await client.post(
        f"/api/v1/users/{agent_id}/ip-restriction", json={"allowed_ip": None}, headers=admin
    )
    assert cleared.status_code == 200, cleared.text

    assert (await _login(client, "unpin.agent@example.com", ELSEWHERE)).status_code == 200


async def test_admin_can_read_the_address_the_server_sees(
    client: AsyncClient, unique_email: str
):
    tokens = await _register_org(client, "MyIp Org", unique_email)
    resp = await client.get("/api/v1/users/my-ip", headers=_auth(tokens["access_token"], OFFICE))
    assert resp.status_code == 200, resp.text
    assert resp.json()["address"] == OFFICE
