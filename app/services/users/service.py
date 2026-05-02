from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_repository import UserRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.db.models import User, ActorType
from app.core.config import settings


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.audit_repo = AuditLogRepository(session)

    async def get_or_register(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
    ) -> tuple[User, bool]:
        """Get existing user or register a new one."""
        user, is_new = await self.user_repo.get_or_create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
        )

        # Auto-assign admin if in ADMIN_IDS
        if telegram_id in settings.admin_ids and not user.is_admin:
            user.is_admin = True
            await self.session.flush()

        if is_new:
            await self.audit_repo.log(
                actor_type=ActorType.USER,
                actor_id=telegram_id,
                action="user_registered",
                entity_type="user",
                entity_id=user.id,
            )

        return user, is_new

    async def can_use_free_preview(self, user: User) -> bool:
        return user.free_previews_used < settings.free_previews_limit

    async def block(self, telegram_id: int, admin_id: int) -> None:
        await self.user_repo.set_blocked(telegram_id, True)
        await self.audit_repo.log(
            actor_type=ActorType.ADMIN,
            actor_id=admin_id,
            action="user_blocked",
            entity_type="user",
            payload={"telegram_id": telegram_id},
        )

    async def unblock(self, telegram_id: int, admin_id: int) -> None:
        await self.user_repo.set_blocked(telegram_id, False)
        await self.audit_repo.log(
            actor_type=ActorType.ADMIN,
            actor_id=admin_id,
            action="user_unblocked",
            entity_type="user",
            payload={"telegram_id": telegram_id},
        )
