"""
Idempotent seed script for platform-global data: system roles and
permissions. Run once per environment (dev/staging/prod) after migrations:

    python -m app.seed

Without this, AuthService.register_organization will fail because it looks
up the 'org_admin' system role and finds nothing.
"""
import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.organizations.models import Organization  # noqa: F401 — registers table for FK resolution
from app.modules.roles_permissions.models import Permission, Role

SYSTEM_ROLES = ["super_admin", "org_admin", "team_manager", "agent"]

# Initial permission set — matches the module list in the architecture doc.
# More are added as later modules (tickets, knowledge_base, etc.) are built.
PERMISSIONS = [
    ("organizations.manage", "Create/update/suspend organizations (Super Admin only)"),
    ("users.manage", "Invite, update, deactivate users within an organization"),
    ("departments.manage", "Create/update/delete departments"),
    ("teams.manage", "Create/update/delete teams and team membership"),
    ("roles.manage", "Create custom roles and assign permissions"),
    ("conversations.view", "View conversations"),
    ("conversations.assign", "Assign/transfer conversations between agents"),
    ("conversations.close", "Close a conversation"),
    ("tickets.manage", "Create, update, and close tickets"),
    ("reports.view", "View analytics and reports"),
    ("settings.manage", "Modify organization-level settings"),
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        for code, description in PERMISSIONS:
            existing = await session.execute(select(Permission).where(Permission.code == code))
            if existing.scalar_one_or_none() is None:
                session.add(Permission(code=code, description=description))

        for role_name in SYSTEM_ROLES:
            existing = await session.execute(
                select(Role).where(Role.name == role_name, Role.organization_id.is_(None))
            )
            if existing.scalar_one_or_none() is None:
                session.add(Role(name=role_name, organization_id=None, is_system_role=True))

        await session.commit()
        print(f"Seeded {len(PERMISSIONS)} permissions and {len(SYSTEM_ROLES)} system roles.")


if __name__ == "__main__":
    asyncio.run(seed())
