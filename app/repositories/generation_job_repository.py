from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.db.models import GenerationJob, GenerationJobStatus


class GenerationJobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, project_id: int) -> GenerationJob:
        job = GenerationJob(
            project_id=project_id,
            status=GenerationJobStatus.PENDING,
            attempts=0,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_by_id(self, job_id: int) -> Optional[GenerationJob]:
        result = await self.session.execute(
            select(GenerationJob).where(GenerationJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_for_project(self, project_id: int) -> Optional[GenerationJob]:
        result = await self.session.execute(
            select(GenerationJob)
            .where(GenerationJob.project_id == project_id)
            .order_by(GenerationJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def set_running(self, job_id: int, celery_task_id: str) -> None:
        await self.session.execute(
            update(GenerationJob)
            .where(GenerationJob.id == job_id)
            .values(
                status=GenerationJobStatus.RUNNING,
                celery_task_id=celery_task_id,
                started_at=datetime.now(timezone.utc),
                attempts=GenerationJob.attempts + 1,
            )
        )

    async def set_done(self, job_id: int) -> None:
        await self.session.execute(
            update(GenerationJob)
            .where(GenerationJob.id == job_id)
            .values(
                status=GenerationJobStatus.DONE,
                finished_at=datetime.now(timezone.utc),
            )
        )

    async def set_failed(self, job_id: int, error_message: str) -> None:
        await self.session.execute(
            update(GenerationJob)
            .where(GenerationJob.id == job_id)
            .values(
                status=GenerationJobStatus.FAILED,
                finished_at=datetime.now(timezone.utc),
                error_message=error_message,
            )
        )
