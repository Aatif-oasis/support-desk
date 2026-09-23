"""
Creates a ready-to-use demo organization so that anyone who clones this
repo can log in immediately instead of having to craft a registration
API call by hand.

    python -m app.seed_demo

Safe to run more than once — if the demo org already exists it says so
and changes nothing.

Credentials it creates (development only — never run this in production):

    Organization : Demo Company     (slug: demo-company)
    Admin        : admin@demo.com / DemoPass123
    Agent        : agent@demo.com / DemoPass123

Run this AFTER `alembic upgrade head` and `python -m app.seed`, because
registration looks up the org_admin system role that app.seed creates.
"""
import asyncio

from app.core.database import AsyncSessionLocal
from app.core.exceptions import ConflictError
from app.modules.auth.schemas import RegisterOrganizationRequest
from app.modules.auth.service import AuthService
from app.modules.users.schemas import UserInviteRequest
from app.modules.users.service import UserService

ORG_NAME = "Demo Company"
ADMIN_EMAIL = "admin@demo.com"
AGENT_EMAIL = "agent@demo.com"
PASSWORD = "DemoPass123"


async def seed_demo() -> None:
    async with AsyncSessionLocal() as session:
        auth_service = AuthService(session)

        try:
            await auth_service.register_organization(
                RegisterOrganizationRequest(
                    organization_name=ORG_NAME,
                    admin_full_name="Demo Admin",
                    admin_email=ADMIN_EMAIL,
                    admin_password=PASSWORD,
                )
            )
        except ConflictError:
            print("Demo organization already exists — nothing to do.")
            print(f"  Login: {ADMIN_EMAIL} / {PASSWORD}")
            return

        # The admin was just created, so fetch it to get the organization id
        # that the agent invite needs.
        admin = await auth_service.user_repo.get_by_email(ADMIN_EMAIL)

        try:
            await UserService(session, admin.organization_id).invite_user(
                admin.id,
                UserInviteRequest(
                    email=AGENT_EMAIL,
                    full_name="Demo Agent",
                    temporary_password=PASSWORD,
                    role="agent",
                ),
            )
        except ConflictError as exc:
            # An agent is a convenience, not a requirement — the demo is
            # still usable with just the admin account.
            print(f"Note: could not create the demo agent ({exc}). Admin login still works.")

        print("Demo data created.")
        print(f"  Organization : {ORG_NAME}  (widget slug: demo-company)")
        print(f"  Admin        : {ADMIN_EMAIL} / {PASSWORD}")
        print(f"  Agent        : {AGENT_EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed_demo())
