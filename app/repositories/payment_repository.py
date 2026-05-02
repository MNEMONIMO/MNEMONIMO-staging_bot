from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, PaymentStatus, Tariff


class PaymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        project_id: int,
        user_id: int,
        tariff: Tariff,
        amount: int,
        provider: str = "telegram",
        currency: str = "RUB",
    ) -> Payment:
        payment = Payment(
            project_id=project_id,
            user_id=user_id,
            tariff=tariff,
            amount=amount,
            provider=provider,
            currency=currency,
            status=PaymentStatus.PENDING,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_by_id(self, payment_id: int) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.external_payment_id == external_id)
        )
        return result.scalar_one_or_none()

    async def set_status(
        self,
        payment_id: int,
        status: PaymentStatus,
        external_payment_id: Optional[str] = None,
    ) -> None:
        values = {"status": status}
        if external_payment_id:
            values["external_payment_id"] = external_payment_id
        await self.session.execute(
            update(Payment).where(Payment.id == payment_id).values(**values)
        )

    async def get_project_payments(self, project_id: int) -> List[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.project_id == project_id)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())
