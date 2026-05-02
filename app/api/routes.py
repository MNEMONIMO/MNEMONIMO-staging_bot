from fastapi import FastAPI, Depends, HTTPException, Header
from typing import List, Optional

from app.core.config import settings
from app.db.session import get_db, AsyncSession
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.services.generation.service import GenerationService
from app.services.notification.service import NotificationService
from app.schemas.schemas import (
    ProjectOut, ProjectSummary, UserOut, StatsOut, BroadcastRequest
)
from app.db.models import ProjectStatus

api = FastAPI(title="Staging Bot Admin API", version="1.0.0")


async def verify_admin_token(x_admin_token: str = Header(...)):
    """Simple token-based auth for internal API."""
    if x_admin_token != settings.bot_token:  # reuse bot token as internal secret
        raise HTTPException(status_code=401, detail="Invalid token")
    return True


# ─── Projects ─────────────────────────────────────────────────────────────────

@api.get("/projects", response_model=List[ProjectSummary])
async def list_projects(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    _: bool = Depends(verify_admin_token),
    session: AsyncSession = Depends(get_db),
):
    repo = ProjectRepository(session)
    return await repo.list_all(status=status, limit=limit, offset=offset)


@api.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: int,
    _: bool = Depends(verify_admin_token),
    session: AsyncSession = Depends(get_db),
):
    project = await ProjectRepository(session).get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@api.post("/projects/{project_id}/retry")
async def retry_generation(
    project_id: int,
    _: bool = Depends(verify_admin_token),
    session: AsyncSession = Depends(get_db),
):
    service = GenerationService(session)
    job_id = await service.enqueue(project_id)
    return {"status": "queued", "job_id": job_id}


@api.post("/projects/{project_id}/cancel")
async def cancel_project(
    project_id: int,
    _: bool = Depends(verify_admin_token),
    session: AsyncSession = Depends(get_db),
):
    await ProjectRepository(session).set_status(project_id, ProjectStatus.CANCELLED)
    return {"status": "cancelled"}


# ─── Users ────────────────────────────────────────────────────────────────────

@api.get("/users", response_model=List[UserOut])
async def list_users(
    limit: int = 100,
    _: bool = Depends(verify_admin_token),
    session: AsyncSession = Depends(get_db),
):
    return await UserRepository(session).list_all(limit=limit)


@api.post("/users/{telegram_id}/block")
async def block_user(
    telegram_id: int,
    _: bool = Depends(verify_admin_token),
    session: AsyncSession = Depends(get_db),
):
    await UserRepository(session).set_blocked(telegram_id, True)
    return {"status": "blocked"}


@api.post("/users/{telegram_id}/unblock")
async def unblock_user(
    telegram_id: int,
    _: bool = Depends(verify_admin_token),
    session: AsyncSession = Depends(get_db),
):
    await UserRepository(session).set_blocked(telegram_id, False)
    return {"status": "unblocked"}


# ─── Stats ────────────────────────────────────────────────────────────────────

@api.get("/stats", response_model=StatsOut)
async def get_stats(
    _: bool = Depends(verify_admin_token),
    session: AsyncSession = Depends(get_db),
):
    project_repo = ProjectRepository(session)
    user_repo = UserRepository(session)

    status_counts = await project_repo.count_by_status()
    users = await user_repo.list_all(limit=100000)

    return StatsOut(
        total_users=len(users),
        total_projects=sum(status_counts.values()),
        projects_done=status_counts.get(ProjectStatus.DONE, 0),
        projects_failed=status_counts.get(ProjectStatus.FAILED, 0),
        projects_by_status=status_counts,
    )


# ─── Broadcast ────────────────────────────────────────────────────────────────

@api.post("/broadcast")
async def broadcast(
    req: BroadcastRequest,
    _: bool = Depends(verify_admin_token),
    session: AsyncSession = Depends(get_db),
):
    users = await UserRepository(session).list_all(limit=100000)
    ids = [u.telegram_id for u in users if not u.is_blocked]

    notifier = NotificationService()
    result = await notifier.broadcast(req.text, ids)
    return result
