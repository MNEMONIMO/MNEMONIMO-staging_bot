import asyncio
from loguru import logger
from app.workers.celery_app import celery_app
from app.db.session import AsyncSessionLocal


@celery_app.task(
    bind=True,
    name="generation.run",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def run_generation_task(self, project_id: int, job_id: int):
    """Celery task: run full generation pipeline for a project."""
    logger.info(f"[Task] Starting generation for project={project_id} job={job_id}")

    async def _run():
        from app.services.generation.service import GenerationService
        async with AsyncSessionLocal() as session:
            service = GenerationService(session)
            await service.execute(project_id, job_id)

        # Notify the user via bot after completion
        await _notify_user(project_id)

    async def _notify_user(project_id: int):
        """Send result to user via Telegram."""
        try:
            from app.db.session import AsyncSessionLocal
            from app.repositories.project_repository import ProjectRepository
            from app.services.notification.service import NotificationService

            async with AsyncSessionLocal() as session:
                repo = ProjectRepository(session)
                project = await repo.get_by_id(project_id)
                if project:
                    notifier = NotificationService()
                    await notifier.send_generation_result(project)
        except Exception as e:
            logger.error(f"Failed to notify user for project {project_id}: {e}")

    try:
        asyncio.run(_run())
        logger.info(f"[Task] Generation completed for project={project_id}")
    except Exception as exc:
        logger.error(f"[Task] Generation failed for project={project_id}: {exc}")
        raise self.retry(exc=exc)
