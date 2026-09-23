"""
Test fixtures use in-memory SQLite instead of Postgres so the suite runs
anywhere with zero external services — this is what CI will use. Postgres-
specific behavior (JSONB, etc.) is exercised separately via the Alembic
migration itself being run against real Postgres, not via this suite.
"""
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from app.core.config import settings
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.redis import get_redis
from app.main import app
from app.modules.organizations.models import Organization  # noqa: F401
from app.modules.departments.models import Department  # noqa: F401
from app.modules.teams.models import Team  # noqa: F401
from app.modules.users.models import User  # noqa: F401
from app.modules.roles_permissions.models import Permission, Role  # noqa: F401
from app.modules.auth.models import ApiKey, RefreshToken  # noqa: F401
from app.modules.customers.models import Customer  # noqa: F401
from app.modules.conversations.models import Conversation, ConversationNote, Message, Tag, conversation_tags  # noqa: F401
from app.modules.attachments.models import Attachment  # noqa: F401
from app.modules.quick_replies.models import QuickReply  # noqa: F401
from app.modules.tickets.models import Ticket, TicketComment  # noqa: F401
from app.modules.notifications.models import Notification  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def isolate_deployment_settings():
    """
    Pins the settings a test run depends on, rather than inheriting them
    from whatever .env is on the machine.

    Without this, switching captcha on for a local deployment silently
    broke a dozen unrelated tests — the suite was reporting on the
    machine's configuration instead of on the code.
    """
    saved = (settings.CAPTCHA_ENABLED, settings.TRUST_FORWARDED_FOR)
    settings.CAPTCHA_ENABLED = False
    settings.TRUST_FORWARDED_FOR = False
    yield
    settings.CAPTCHA_ENABLED, settings.TRUST_FORWARDED_FOR = saved


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        # Seed the system roles every test needs — mirrors app/seed.py but
        # scoped to this ephemeral test DB.
        for role_name in ["super_admin", "org_admin", "team_manager", "agent"]:
            session.add(Role(name=role_name, organization_id=None, is_system_role=True))
        await session.commit()
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    # A fresh connection per test, not the module-level singleton in
    # app.core.redis — that singleton is created once at import time and
    # binds to whichever event loop existed then. pytest-asyncio gives each
    # test function its own event loop, so reusing the singleton across
    # tests throws "Future attached to a different loop". Creating one here
    # ties it to the current test's loop instead.
    from app.core.config import settings

    try:
        # Prefer a real Redis when one is running, since that is what the
        # app talks to in production. Fall back to an in-process fake so
        # the suite still runs on a machine (or CI box) without Redis —
        # the alternative is every conversation test failing for a reason
        # that has nothing to do with the code under test.
        import fakeredis.aioredis

        test_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    except ImportError:
        from redis.asyncio import from_url

        test_redis = from_url(settings.REDIS_URL, decode_responses=True)

    async def override_get_redis():
        return test_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    from app.core.rate_limit import (
        attachment_upload_rate_limit,
        conversation_start_rate_limit,
        identify_rate_limit,
        kb_public_rate_limit,
        message_send_rate_limit,
    )

    async def _no_rate_limit():
        return None

    for limiter in (
        identify_rate_limit,
        conversation_start_rate_limit,
        message_send_rate_limit,
        kb_public_rate_limit,
        attachment_upload_rate_limit,
    ):
        app.dependency_overrides[limiter] = _no_rate_limit
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await test_redis.aclose()


@pytest.fixture
def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:8]}@example.com"
from app.modules.knowledge_base.models import KnowledgeBaseArticle, KnowledgeBaseCategory  # noqa: F401
from app.modules.automation.models import AutomationRule  # noqa: F401
from app.modules.audit_logs.models import AuditLog  # noqa: F401
from app.modules.webhooks.models import WebhookDelivery, WebhookSubscription  # noqa: F401
