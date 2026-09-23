import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.modules.audit_logs.service import AuditLogService
from app.modules.roles_permissions.repository import RoleRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserInviteRequest, UserUpdateRequest


class UserService:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        self.session = session
        self.organization_id = organization_id
        self.repo = UserRepository(session, organization_id=organization_id)
        self.role_repo = RoleRepository(session)
        self.audit_service = AuditLogService(session, organization_id)

    async def list_users(self, limit: int, offset: int) -> list[tuple[User, list[str]]]:
        users = await self.repo.list(limit=limit, offset=offset)
        return [(u, await self.role_repo.get_role_names_for_user(u.id)) for u in users]

    async def get_user(self, user_id: uuid.UUID) -> tuple[User, list[str]]:
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found.")
        roles = await self.role_repo.get_role_names_for_user(user.id)
        return user, roles

    async def invite_user(self, actor_user_id: uuid.UUID, request: UserInviteRequest) -> tuple[User, list[str]]:
        existing = await self.repo.get_by_email(request.email)
        if existing:
            raise ConflictError("An account with this email already exists.")

        user = await self.repo.create(
            User(
                organization_id=self.organization_id,
                email=request.email,
                password_hash=hash_password(request.temporary_password),
                full_name=request.full_name,
                status="invited",
            )
        )

        role = await self.role_repo.get_system_role_by_name(request.role)
        if not role:
            raise NotFoundError(f"System role '{request.role}' is missing — run seed data.")
        await self.role_repo.assign_role_to_user(user.id, role.id)
        await self.audit_service.log(actor_user_id, "user.invited", "user", user.id, {"email": request.email, "role": request.role})

        await self.session.commit()
        return user, [request.role]

    async def update_user(self, user_id: uuid.UUID, request: UserUpdateRequest) -> tuple[User, list[str]]:
        user, roles = await self.get_user(user_id)
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        await self.repo.update(user)
        await self.session.commit()
        return user, roles

    async def set_allowed_ip(
        self, actor_user_id: uuid.UUID, user_id: uuid.UUID, allowed_ip: str | None
    ) -> User:
        """
        Pins an account to one address, or clears it. Clearing is how an
        admin lets someone work from home for a week without deleting and
        recreating anything.
        """
        user, _ = await self.get_user(user_id)
        user.allowed_ip = (allowed_ip or "").strip() or None

        # A previous blocked attempt is about the old address; keeping it
        # around after a move would leave a stale warning on the screen.
        user.last_blocked_ip = None
        user.last_blocked_at = None

        await self.repo.update(user)
        await self.audit_service.log(
            actor_user_id,
            "user.ip_restriction_changed",
            "user",
            user_id,
            {"allowed_ip": user.allowed_ip},
        )
        await self.session.commit()
        return user

    async def reset_password(
        self, actor_user_id: uuid.UUID, user_id: uuid.UUID, new_password: str
    ) -> User:
        """
        The answer to "an agent forgot their password". Nobody, including
        an admin, can read the old one — only a hash is stored — so the
        only possible help is to set a new one and tell them what it is.

        The account is moved back to 'invited', which is the same state a
        brand new user is in: it is a plain record that this password came
        from an admin, not from the person who owns the account.
        """
        user, _ = await self.get_user(user_id)
        user.password_hash = hash_password(new_password)
        user.status = "invited"
        await self.repo.update(user)
        await self.audit_service.log(
            actor_user_id, "user.password_reset", "user", user_id, {"email": user.email}
        )
        await self.session.commit()
        return user

    async def reactivate_user(self, actor_user_id: uuid.UUID, user_id: uuid.UUID) -> User:
        user, _ = await self.get_user(user_id)
        user.status = "active"
        await self.repo.update(user)
        await self.audit_service.log(actor_user_id, "user.reactivated", "user", user_id, {})
        await self.session.commit()
        return user

    async def deactivate_user(self, actor_user_id: uuid.UUID, user_id: uuid.UUID) -> None:
        user, _ = await self.get_user(user_id)
        user.status = "suspended"
        await self.repo.update(user)
        await self.audit_service.log(actor_user_id, "user.deactivated", "user", user_id, {})
        await self.session.commit()

    async def assign_role(self, actor_user_id: uuid.UUID, user_id: uuid.UUID, role_name: str) -> list[str]:
        user, current_roles = await self.get_user(user_id)
        if role_name in current_roles:
            return current_roles
        role = await self.role_repo.get_system_role_by_name(role_name)
        if not role:
            raise NotFoundError(f"System role '{role_name}' is missing — run seed data.")
        await self.role_repo.assign_role_to_user(user.id, role.id)
        await self.audit_service.log(actor_user_id, "user.role_assigned", "user", user_id, {"role": role_name})
        await self.session.commit()
        return await self.role_repo.get_role_names_for_user(user.id)
