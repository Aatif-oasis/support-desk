"""
Pre-chat verification.

Two things are being protected here. One is that the answer is checked on
the server: a widget can be edited by anyone, so a captcha that only lives
in the browser protects nothing. The other is *where* it is checked — at
the form, while the visitor is still looking at the question, rather than
later when they send a message and get told the message failed.
"""
import pytest
from httpx import AsyncClient

from app.core.config import settings

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


def _start_payload(external_id: str, **extra) -> dict:
    return {
        "external_id": external_id,
        "initial_message": "Hello",
        "full_name": "Asha Rao",
        "phone": "+919720961466",
        **extra,
    }


async def _fresh_challenge(client: AsyncClient, slug: str) -> tuple[str, int]:
    resp = await client.get(f"/api/v1/public/{slug}/conversations/captcha")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    left, right = body["question"].split("+")
    return body["challenge_id"], int(left.strip()) + int(right.strip())


@pytest.fixture
def captcha_on():
    settings.CAPTCHA_ENABLED = True
    yield
    settings.CAPTCHA_ENABLED = False


async def test_a_correct_answer_returns_a_pass_that_starts_a_chat(
    client: AsyncClient, unique_email: str, captcha_on
):
    org = "Captcha Org"
    await _register_org(client, org, unique_email)
    slug = _slug(org)

    challenge_id, answer = await _fresh_challenge(client, slug)

    verified = await client.post(
        f"/api/v1/public/{slug}/conversations/captcha/verify",
        json={"challenge_id": challenge_id, "answer": str(answer)},
    )
    assert verified.status_code == 200, verified.text
    captcha_pass = verified.json()["captcha_pass"]

    start = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json=_start_payload("visitor-captcha-1", captcha_pass=captcha_pass),
    )
    assert start.status_code == 201, start.text


async def test_a_wrong_answer_is_rejected_at_the_form(
    client: AsyncClient, unique_email: str, captcha_on
):
    """The failure has to happen here, not when the first message is sent."""
    org = "Captcha Wrong Org"
    await _register_org(client, org, unique_email)
    slug = _slug(org)

    challenge_id, answer = await _fresh_challenge(client, slug)

    resp = await client.post(
        f"/api/v1/public/{slug}/conversations/captcha/verify",
        json={"challenge_id": challenge_id, "answer": str(answer + 1)},
    )
    assert resp.status_code == 422, resp.text
    assert "right" in resp.text.lower() or "answer" in resp.text.lower()


async def test_a_challenge_cannot_be_answered_twice(
    client: AsyncClient, unique_email: str, captcha_on
):
    org = "Captcha Replay Org"
    await _register_org(client, org, unique_email)
    slug = _slug(org)

    challenge_id, answer = await _fresh_challenge(client, slug)
    first = await client.post(
        f"/api/v1/public/{slug}/conversations/captcha/verify",
        json={"challenge_id": challenge_id, "answer": str(answer)},
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/v1/public/{slug}/conversations/captcha/verify",
        json={"challenge_id": challenge_id, "answer": str(answer)},
    )
    assert second.status_code == 422, second.text


async def test_a_pass_cannot_be_spent_twice(client: AsyncClient, unique_email: str, captcha_on):
    org = "Captcha Pass Org"
    await _register_org(client, org, unique_email)
    slug = _slug(org)

    challenge_id, answer = await _fresh_challenge(client, slug)
    captcha_pass = (
        await client.post(
            f"/api/v1/public/{slug}/conversations/captcha/verify",
            json={"challenge_id": challenge_id, "answer": str(answer)},
        )
    ).json()["captcha_pass"]

    first = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json=_start_payload("visitor-captcha-4", captcha_pass=captcha_pass),
    )
    assert first.status_code == 201

    replay = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json=_start_payload("visitor-captcha-5", captcha_pass=captcha_pass),
    )
    assert replay.status_code == 422, replay.text


async def test_starting_without_a_pass_is_rejected(
    client: AsyncClient, unique_email: str, captcha_on
):
    org = "Captcha Missing Org"
    await _register_org(client, org, unique_email)
    slug = _slug(org)

    resp = await client.post(
        f"/api/v1/public/{slug}/conversations", json=_start_payload("visitor-captcha-6")
    )
    assert resp.status_code == 422, resp.text


async def test_chats_still_start_when_captcha_is_off(client: AsyncClient, unique_email: str):
    """Existing embeds must keep working after an upgrade."""
    org = "Captcha Off Org"
    await _register_org(client, org, unique_email)
    slug = _slug(org)

    resp = await client.post(
        f"/api/v1/public/{slug}/conversations", json=_start_payload("visitor-captcha-7")
    )
    assert resp.status_code == 201, resp.text


async def test_phone_must_have_the_right_number_of_digits(client: AsyncClient, unique_email: str):
    """
    The widget checks this while the visitor types, but the widget is
    JavaScript on someone else's page. The rule has to hold here too.
    """
    org = "Phone Length Org"
    await _register_org(client, org, unique_email)
    slug = _slug(org)

    too_short = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json=_start_payload("visitor-phone-1", phone="+4479123456"),
    )
    assert too_short.status_code == 422, too_short.text
    assert "10 digits" in too_short.text

    # Australian mobiles are nine digits — a flat "must be ten" would lock
    # out an entire country.
    australian = await client.post(
        f"/api/v1/public/{slug}/conversations",
        json=_start_payload("visitor-phone-2", phone="+61412345678"),
    )
    assert australian.status_code == 201, australian.text
