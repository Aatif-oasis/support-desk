"""
Create the platform owner account — the one login that can see and
manage every client's organization, not just one.

    python -m app.create_super_admin

Run this once, on the server itself, after the very first setup. Unlike
every other user in the system, a super_admin has organization_id = NULL:
they don't belong to a tenant, they sit above all of them. Because of
that, this account should never be handed to a client or an agent — it
is for whoever runs the platform.
"""
import asyncio
import getpass
import sys

import app.main  # noqa: F401

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.modules.roles_permissions.repository import RoleRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository


def ask(label: str, minimum: int = 1) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if len(value) >= minimum:
            return value
        print(f"  Needs at least {minimum} characters.")


def ask_password() -> str:
    while True:
        first = getpass.getpass("Password (hidden as you type): ")
        if len(first) < 8:
            print("  Needs at least 8 characters.")
            continue
        if first != getpass.getpass("Type it again: "):
            print("  Those didn't match.")
            continue
        return first


async def create() -> None:
    print("\nNew platform admin (super_admin)\n")
    print("This account is not tied to any one client — it can see and")
    print("suspend every organization on this server. Keep it for")
    print("yourself, not for a client or an agent.\n")

    full_name = ask("Full name", 2)
    email = ask("Email", 5)

    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)

        existing = await user_repo.get_by_email(email)
        if existing:
            print(f"\nNot created: a user with '{email}' already exists.")
            sys.exit(1)

        role_repo = RoleRepository(session)
        role = await role_repo.get_system_role_by_name("super_admin")
        if not role:
            print("\nNot created: the 'super_admin' system role is missing.")
            print("Run  python -m app.seed  first, then try again.")
            sys.exit(1)

        password = ask_password()

        # organization_id is left unset (NULL) deliberately — that is
        # what marks this account as platform-level rather than scoped
        # to one tenant. See the note on the User model.
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            status="active",
        )
        session.add(user)
        await session.flush()  # assigns user.id before the role link is written

        await role_repo.assign_role_to_user(user.id, role.id)
        await session.commit()

    print("\nDone.")
    print(f"  Sign in with: {email}")
    print("  This account will land on the Platform screen after login,")
    print("  not the usual agent dashboard.")


if __name__ == "__main__":
    asyncio.run(create())
