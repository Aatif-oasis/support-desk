"""
A small arithmetic challenge for the pre-chat form.

Deliberately not reCAPTCHA. This product is self-hosted, and dropping
Google's script onto every customer's website would send every visitor's
browsing to a third party just to ask "are you a bot" — a poor trade for
software whose main selling point is that the data stays yours.

The answer never leaves the server: the widget receives a question and an
id, and the backend keeps the answer in Redis under that id. A challenge
is single-use and expires, so a captured id cannot be replayed.

This stops scripted form submissions. It will not stop a determined human
with a script — nothing of this size will. The real protection against
volume is the rate limiting already in front of these endpoints.
"""
import random
import uuid

from redis.asyncio import Redis

from app.core.exceptions import ValidationError

_TTL_SECONDS = 300  # five minutes: long enough to type, short enough to expire
_PASS_TTL_SECONDS = 1800  # the visitor still has to type their first message
_KEY = "captcha:{challenge_id}"
_PASS_KEY = "captcha_pass:{token}"


def _key(challenge_id: str) -> str:
    return _KEY.format(challenge_id=challenge_id)


def _pass_key(token: str) -> str:
    return _PASS_KEY.format(token=token)


async def issue_challenge(redis: Redis) -> dict:
    """
    Returns a question for a human and an id for the machine.

    Addition of two small numbers, written in digits: readable on a phone,
    answerable without a calculator, and language-independent, which
    matters because the widget runs on sites in any language.
    """
    left = random.randint(1, 9)
    right = random.randint(1, 9)

    challenge_id = str(uuid.uuid4())
    await redis.setex(_key(challenge_id), _TTL_SECONDS, str(left + right))

    return {"challenge_id": challenge_id, "question": f"{left} + {right}"}


async def verify_and_issue_pass(redis: Redis, challenge_id: str | None, answer: str | None) -> str:
    """
    Checks the answer at the form, where the person is still looking at the
    question, and hands back a pass they can spend later.

    This split exists because the answer used to be checked when the first
    message was sent — by which point the visitor had left the form, and a
    wrong sum came back looking like "your message failed to send". The
    error has to appear next to the field that caused it.
    """
    await verify_challenge(redis, challenge_id, answer)

    token = str(uuid.uuid4())
    await redis.setex(_pass_key(token), _PASS_TTL_SECONDS, "1")
    return token


async def consume_pass(redis: Redis, token: str | None) -> None:
    """Spends a pass issued at the form. Single use, like the challenge."""
    if not token:
        raise ValidationError("Please complete the verification question.")

    stored = await redis.get(_pass_key(token))
    await redis.delete(_pass_key(token))

    if stored is None:
        raise ValidationError("That verification expired. Please refresh and try again.")


async def verify_challenge(redis: Redis, challenge_id: str | None, answer: str | None) -> None:
    """
    Raises ValidationError unless the answer matches. Consumes the
    challenge either way, so a wrong guess costs a fresh round trip rather
    than allowing unlimited attempts against one question.
    """
    if not challenge_id or answer is None:
        raise ValidationError("Please answer the verification question.")

    stored = await redis.get(_key(challenge_id))
    await redis.delete(_key(challenge_id))

    if stored is None:
        raise ValidationError("That verification expired. Please try again.")

    if str(answer).strip() != str(stored).strip():
        raise ValidationError("That answer wasn't right. Please try again.")
