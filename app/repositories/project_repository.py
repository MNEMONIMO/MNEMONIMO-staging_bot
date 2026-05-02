from typing import Optional, List
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Project, ProjectImage, ProjectStatus, ImageType, Tariff


class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, project_id: int) -> Optional[Project]:
        result = await self.session.execute(
            select(Project)
            .options(selectinload(Project.images), selectinload(Project.generation_jobs))
            .where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_user_projects(self, user_id: int, limit: int = 10) -> List[Project]:
        result = await self.session.execute(
            select(Project)
            .options(selectinload(Project.images))
            .where(Project.user_id == user_id)
            .order_by(Project.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_active_projects(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Project.id))
            .where(
                Project.user_id == user_id,
                Project.status.not_in([
                    ProjectStatus.DONE, ProjectStatus.CANCELLED, ProjectStatus.FAILED
                ])
            )
        )
        return result.scalar_one() or 0

    async def create(self, user_id: int) -> Project:
        project = Project(user_id=user_id, status=ProjectStatus.DRAFT)
        self.session.add(project)
        await self.session.flush()
        return project

    async def update_params(self, project_id: int, **kwargs) -> None:
        await self.session.execute(
            update(Project).where(Project.id == project_id).values(**kwargs)
        )

    async def set_status(self, project_id: int, status: ProjectStatus) -> None:
        await self.session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(status=status)
        )

    async def set_result(
        self,
        project_id: int,
        concept_text: str,
        shopping_list: Optional[dict] = None,
    ) -> None:
        await self.session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(
                concept_text=concept_text,
                shopping_list=shopping_list,
                status=ProjectStatus.DONE,
            )
        )

    async def add_image(
        self,
        project_id: int,
        image_type: ImageType,
        file_path: Optional[str] = None,
        file_id_telegram: Optional[str] = None,
        sort_order: int = 0,
    ) -> ProjectImage:
        image = ProjectImage(
            project_id=project_id,
            image_type=image_type,
            file_path=file_path,
            file_id_telegram=file_id_telegram,
            sort_order=sort_order,
        )
        self.session.add(image)
        await self.session.flush()
        return image

    async def delete(self, project_id: int) -> None:
        project = await self.get_by_id(project_id)
        if project:
            await self.session.delete(project)

    async def list_all(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Project]:
        q = select(Project).options(selectinload(Project.user))
        if status:
            q = q.where(Project.status == status)
        q = q.order_by(Project.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def count_by_status(self) -> dict:
        result = await self.session.execute(
            select(Project.status, func.count(Project.id))
            .group_by(Project.status)
        )
        return {row[0]: row[1] for row in result.all()}
