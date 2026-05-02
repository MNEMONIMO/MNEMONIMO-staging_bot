from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import AuditLog, ActorType


class AuditLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        actor_type: ActorType,
        action: str,
        actor_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        payload: Optional[dict] = None,
    ) -> None:
        entry = AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload,
        )
        self.session.add(entry)
        await self.session.flush()
