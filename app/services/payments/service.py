from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.payment_repository import PaymentRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.db.models import Tariff, PaymentStatus, ProjectStatus, ActorType

TARIFF_PRICES = {
    Tariff.FREE: 0,
    Tariff.ROOM: 49900,
    Tariff.PRO_ROOM: 99900,
    Tariff.FLAT: 199900,
    Tariff.REALTOR_PACK: 299900,
}

TARIFF_DESCRIPTIONS = {
    Tariff.FREE: "1 preview, водяной знак",
    Tariff.ROOM: "3 варианта без водяного знака, базовый shopping list",
    Tariff.PRO_ROOM: "4 варианта, расширенная концепция, полный shopping list",
    Tariff.FLAT: "Несколько комнат, единая стилистика",
    Tariff.REALTOR_PACK: "Пакет генераций, приоритетная обработка",
}


class PaymentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.payment_repo = PaymentRepository(session)
        self.project_repo = ProjectRepository(session)
        self.audit_repo = AuditLogRepository(session)

    def get_price(self, tariff: Tariff) -> int:
        return TARIFF_PRICES.get(tariff, 0)

    def get_description(self, tariff: Tariff) -> str:
        return TARIFF_DESCRIPTIONS.get(tariff, "")

    async def create_payment(
        self,
        project_id: int,
        user_id: int,
        tariff: Tariff,
    ):
        amount = self.get_price(tariff)
        payment = await self.payment_repo.create(
            project_id=project_id,
            user_id=user_id,
            tariff=tariff,
            amount=amount,
        )
        await self.audit_repo.log(
            actor_type=ActorType.USER,
            actor_id=user_id,
            action="payment_created",
            entity_type="payment",
            entity_id=payment.id,
            payload={"tariff": tariff.value, "amount": amount},
        )
        return payment

    async def confirm_payment(
        self,
        payment_id: int,
        external_payment_id: str,
    ) -> None:
        payment = await self.payment_repo.get_by_id(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        if payment.status == PaymentStatus.SUCCEEDED:
            return  # idempotent

        await self.payment_repo.set_status(
            payment_id,
            PaymentStatus.SUCCEEDED,
            external_payment_id=external_payment_id,
        )
        await self.project_repo.set_status(payment.project_id, ProjectStatus.QUEUED)
        await self.project_repo.update_params(
            payment.project_id, tariff=payment.tariff
        )
        await self.audit_repo.log(
            actor_type=ActorType.SYSTEM,
            action="payment_confirmed",
            entity_type="payment",
            entity_id=payment_id,
            payload={"external_id": external_payment_id},
        )

    async def fail_payment(self, payment_id: int) -> None:
        await self.payment_repo.set_status(payment_id, PaymentStatus.FAILED)
        await self.audit_repo.log(
            actor_type=ActorType.SYSTEM,
            action="payment_failed",
            entity_type="payment",
            entity_id=payment_id,
        )

    async def cancel_payment(self, payment_id: int) -> None:
        await self.payment_repo.set_status(payment_id, PaymentStatus.CANCELLED)
