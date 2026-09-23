"""
Create an organization and its first admin from the server itself.

    python -m app.create_org

Use this when handing the system to a new client. It talks to the database
directly, so it works even when /auth/register is locked behind a setup key
— and it never puts a password into a URL, a shell history file or a proxy
log, which a curl command inevitably does.

Anyone who can run this already has the database credentials, so there is
nothing extra to protect here.
"""
import asyncio
import getpass
import sys

from app.core.database import AsyncSessionLocal
from app.core.exceptions import ConflictError
from app.modules.auth.schemas import RegisterOrganizationRequest
from app.modules.auth.service import AuthService


def ask(label: str, minimum: int = 1) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if len(value) >= minimum:
            return value
        print(f"  Needs at least {minimum} characters.")


def ask_password() -> str:
    while True:
        first = getpass.getpass("Admin password (hidden as you type): ")
        if len(first) < 8:
            print("  Needs at least 8 characters.")
            continue
        if first != getpass.getpass("Type it again: "):
            print("  Those didn't match.")
            continue
        return first


async def create() -> None:
    print("\nNew organization\n")
    organization_name = ask("Organization name", 2)
    admin_full_name = ask("Admin full name", 2)
    admin_email = ask("Admin email", 5)
    admin_password = ask_password()

    async with AsyncSessionLocal() as session:
        try:
            await AuthService(session).register_organization(
                RegisterOrganizationRequest(
                    organization_name=organization_name,
                    admin_full_name=admin_full_name,
                    admin_email=admin_email,
                    admin_password=admin_password,
                )
            )
        except ConflictError as exc:
            print(f"\nNot created: {exc}")
            sys.exit(1)

    slug = "-".join(organization_name.lower().split())
    print("\nDone.")
    print(f"  Sign in with : {admin_email}")
    print(f"  Widget slug  : {slug}")
    print(f'\nPut this on the client\'s website:\n  data-org-slug="{slug}"\n')


if __name__ == "__main__":
    asyncio.run(create())
