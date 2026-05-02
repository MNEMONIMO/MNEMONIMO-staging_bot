from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Project, ProjectStatus, ImageType, Tariff
from app.repositories.project_repository import ProjectRepository
from app.repositories.generation_job_repository import GenerationJobRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.db.models import ActorType
from app.integrations.ai.client import ai_client
from app.integrations.storage.s3 import storage_service
from app.utils.watermark import add_watermark


TARIFF_VARIANTS = {
    Tariff.FREE: 1,
    Tariff.ROOM: 3,
    Tariff.PRO_ROOM: 4,
    Tariff.FLAT: 4,
    Tariff.REALTOR_PACK: 4,
}


def build_concept_text(project: Project) -> str:
    """Generate a short concept description based on project parameters."""
    style_names = {
        "japandi": "Джапанди",
        "minimalism": "Минимализм",
        "modern": "Современный",
        "scandinavian": "Скандинавский",
        "loft": "Лофт",
        "neoclassic": "Неоклассика",
        "cozy_light": "Светлый уютный",
    }
    budget_names = {
        "minimal": "минимальный",
        "medium": "средний",
        "above_medium": "выше среднего",
        "premium": "премиум",
    }
    style = style_names.get(project.style or "", "Современный")
    budget = budget_names.get(project.budget_tier or "", "средний")
    space = project.free_space_percent or "40"

    lines = [
        f"🎨 <b>Стиль:</b> {style}",
        f"💡 <b>Идея:</b> Пространство оформлено в духе {style.lower()} — "
        f"баланс функциональности и эстетики.",
        f"🚶 <b>Свободное пространство:</b> {space}% площади оставлено для свободного прохода.",
        "✨ <b>Акценты:</b> Натуральные материалы, продуманное освещение, "
        "стилевая консистентность.",
        f"💰 <b>Бюджет:</b> Подобрано с учётом {budget} ценового сегмента.",
    ]
    if project.extra_notes:
        lines.append(f"📝 <b>Учтено:</b> {project.extra_notes}")

    return "\n".join(lines)


def build_shopping_list(project: Project) -> dict:
    """Generate an approximate shopping list based on style and room type."""
    base_items = {
        "japandi": [
            {"category": "Диван / кресло", "description": "Низкий профиль, натуральная ткань", "color": "Бежевый / серый", "price_range": "30 000 – 80 000 ₽"},
            {"category": "Стол", "description": "Дерево + металл, минималистичный", "color": "Светлый дуб", "price_range": "15 000 – 40 000 ₽"},
            {"category": "Освещение", "description": "Бумажные / тканевые абажуры", "color": "Белый / натуральный", "price_range": "3 000 – 12 000 ₽"},
            {"category": "Текстиль", "description": "Хлопок, лён, тонкая шерсть", "color": "Земляные тона", "price_range": "5 000 – 20 000 ₽"},
            {"category": "Декор", "description": "Живые растения, керамика, дерево", "color": "Натуральный", "price_range": "3 000 – 10 000 ₽"},
        ],
        "minimalism": [
            {"category": "Диван", "description": "Чистые линии, съёмный чехол", "color": "Белый / серый / чёрный", "price_range": "40 000 – 100 000 ₽"},
            {"category": "Хранение", "description": "Встроенные шкафы / системы", "color": "Белый матовый", "price_range": "20 000 – 60 000 ₽"},
            {"category": "Освещение", "description": "Встроенные споты / минималистичный подвес", "color": "Белый", "price_range": "5 000 – 25 000 ₽"},
            {"category": "Пол", "description": "Ламинат или паркет", "color": "Светлый, однотонный", "price_range": "800 – 2 500 ₽/м²"},
        ],
    }

    style = project.style or "modern"
    items = base_items.get(
        style,
        [
            {"category": "Мебель", "description": "Подобрать в выбранном стиле", "color": "По концепции", "price_range": "Индивидуально"},
            {"category": "Освещение", "description": "Подвес + локальные акценты", "color": "По концепции", "price_range": "5 000 – 20 000 ₽"},
            {"category": "Текстиль", "description": "Шторы, подушки, ковёр", "color": "По концепции", "price_range": "5 000 – 30 000 ₽"},
            {"category": "Декор", "description": "Растения, картины, аксессуары", "color": "По концепции", "price_range": "3 000 – 15 000 ₽"},
        ]
    )
    return {"items": items}


class GenerationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.project_repo = ProjectRepository(session)
        self.job_repo = GenerationJobRepository(session)
        self.audit_repo = AuditLogRepository(session)

    def get_variant_count(self, tariff: str) -> int:
        return TARIFF_VARIANTS.get(Tariff(tariff), 1)

    def needs_watermark(self, tariff: str) -> bool:
        return tariff == Tariff.FREE

    def has_shopping_list(self, tariff: str) -> bool:
        return tariff not in (Tariff.FREE,)

    async def enqueue(self, project_id: int) -> int:
        """Create a generation job and enqueue it. Returns job_id."""
        job = await self.job_repo.create(project_id)
        await self.project_repo.set_status(project_id, ProjectStatus.QUEUED)
        await self.audit_repo.log(
            ActorType.SYSTEM, "generation_enqueued",
            entity_type="project", entity_id=project_id
        )
        await self.session.commit()

        # Import here to avoid circular imports
        from app.workers.tasks.generation import run_generation_task
        result = run_generation_task.delay(project_id, job.id)

        await self.job_repo.set_running(job.id, result.id)
        await self.session.commit()
        return job.id

    async def execute(self, project_id: int, job_id: int) -> None:
        """Run the full generation pipeline. Called from Celery worker."""
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        try:
            # ── Step 1: Vision analysis ──────────────────────────────────────
            await self.project_repo.set_status(project_id, ProjectStatus.ANALYZING)
            await self.session.commit()

            input_photos = project.input_photos
            if not input_photos:
                raise ValueError("No input photos found")

            # Download first photo for analysis
            primary_photo_bytes = storage_service.download_bytes(input_photos[0].file_path)
            analysis = await ai_client.analyze_photo(primary_photo_bytes)
            logger.info(f"Vision analysis for project {project_id}: {analysis}")

            # ── Step 2: Generate images ──────────────────────────────────────
            await self.project_repo.set_status(project_id, ProjectStatus.GENERATING)
            await self.session.commit()

            num_variants = self.get_variant_count(project.tariff)
            generated_images = await ai_client.generate_interior(
                project=project,
                input_image_bytes=primary_photo_bytes,
                num_variants=num_variants,
            )

            # ── Step 3: Postprocessing ───────────────────────────────────────
            await self.project_repo.set_status(project_id, ProjectStatus.POSTPROCESSING)
            await self.session.commit()

            apply_watermark = self.needs_watermark(project.tariff)
            output_paths = []

            for idx, img_bytes in enumerate(generated_images):
                if apply_watermark:
                    img_bytes = add_watermark(img_bytes)

                path = storage_service.upload_bytes(
                    data=img_bytes,
                    prefix=f"outputs/{project_id}",
                    extension="jpg",
                )
                output_paths.append(path)
                await self.project_repo.add_image(
                    project_id=project_id,
                    image_type=ImageType.OUTPUT,
                    file_path=path,
                    sort_order=idx,
                )

            # ── Step 4: Concept text + shopping list ─────────────────────────
            concept = build_concept_text(project)
            shopping_list = (
                build_shopping_list(project)
                if self.has_shopping_list(project.tariff)
                else None
            )

            await self.project_repo.set_result(
                project_id=project_id,
                concept_text=concept,
                shopping_list=shopping_list,
            )

            await self.job_repo.set_done(job_id)
            await self.audit_repo.log(
                ActorType.SYSTEM, "generation_completed",
                entity_type="project", entity_id=project_id,
                payload={"variants": len(output_paths)}
            )
            await self.session.commit()
            logger.info(f"Generation completed for project {project_id}, {len(output_paths)} variants")

        except Exception as e:
            logger.error(f"Generation failed for project {project_id}: {e}")
            await self.job_repo.set_failed(job_id, str(e))
            await self.project_repo.set_status(project_id, ProjectStatus.FAILED)
            await self.audit_repo.log(
                ActorType.SYSTEM, "generation_failed",
                entity_type="project", entity_id=project_id,
                payload={"error": str(e)}
            )
            await self.session.commit()
            raise
