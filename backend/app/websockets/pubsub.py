"""
Why this file exists: with more than one backend instance behind a load
balancer, the process that handles "agent replies via POST /messages" is
often NOT the process holding the customer's open WebSocket connection.
Publishing straight to ConnectionManager would only reach connections on
that one process. Every process instead publishes to Redis, and every
process also runs the listener below, which re-broadcasts to whatever
local connections it happens to be holding — so it's correct regardless of
how many instances are running, including exactly one (this repo's dev setup).
"""
import json
import logging
import uuid

from redis.asyncio import Redis

from app.websockets.connection_manager import connection_manager

logger = logging.getLogger(__name__)

CONVERSATION_CHANNEL_PREFIX = "conversation:"
ORG_AGENTS_CHANNEL_PREFIX = "org-agents:"


def conversation_channel(conversation_id: uuid.UUID) -> str:
    return f"{CONVERSATION_CHANNEL_PREFIX}{conversation_id}"


def org_agents_channel(organization_id: uuid.UUID) -> str:
    return f"{ORG_AGENTS_CHANNEL_PREFIX}{organization_id}"


async def publish_to_conversation(redis: Redis, conversation_id: uuid.UUID, payload: dict) -> None:
    await redis.publish(conversation_channel(conversation_id), json.dumps(payload))


async def publish_to_org_agents(redis: Redis, organization_id: uuid.UUID, payload: dict) -> None:
    await redis.publish(org_agents_channel(organization_id), json.dumps(payload))


async def run_pubsub_listener(redis: Redis) -> None:
    """
    Started once as a background task at app startup (see main.py lifespan).
    Subscribes to both channel families with wildcard patterns and forwards
    every message to ConnectionManager's LOCAL broadcast methods — the
    actual fan-out to browser sockets always goes through here, never
    directly from the service layer.
    """
    pubsub = redis.pubsub()
    await pubsub.psubscribe(f"{CONVERSATION_CHANNEL_PREFIX}*", f"{ORG_AGENTS_CHANNEL_PREFIX}*")

    try:
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue
            try:
                channel: str = message["channel"]
                payload = json.loads(message["data"])
            except (KeyError, json.JSONDecodeError):
                logger.warning("Discarding malformed pub/sub message: %r", message)
                continue

            if channel.startswith(CONVERSATION_CHANNEL_PREFIX):
                conversation_id = uuid.UUID(channel[len(CONVERSATION_CHANNEL_PREFIX):])
                await connection_manager.broadcast_to_conversation(conversation_id, payload)
            elif channel.startswith(ORG_AGENTS_CHANNEL_PREFIX):
                organization_id = uuid.UUID(channel[len(ORG_AGENTS_CHANNEL_PREFIX):])
                await connection_manager.broadcast_to_org_agents(organization_id, payload)
    finally:
        await pubsub.aclose()
