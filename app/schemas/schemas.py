from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


# ─── User schemas ─────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    is_admin: bool
    is_blocked: bool
    free_previews_used: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Project schemas ──────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    room_type: Optional[str] = None
    area_m2: Optional[float] = Field(None, ge=3, le=200)
    ceiling_height: Optional[float] = Field(None, ge=1.8, le=6.0)
    style: Optional[str] = None
    budget_tier: Optional[str] = None
    free_space_percent: Optional[str] = None
    keep_items: Optional[str] = None
    remove_items: Optional[str] = None
    extra_notes: Optional[str] = None


class ProjectImageOut(BaseModel):
    id: int
    image_type: str
    file_path: Optional[str]
    sort_order: int

    model_config = {"from_attributes": True}


class ProjectOut(BaseModel):
    id: int
    user_id: int
    room_type: Optional[str]
    area_m2: Optional[float]
    ceiling_height: Optional[float]
    style: Optional[str]
    budget_tier: Optional[str]
    free_space_percent: Optional[str]
    keep_items: Optional[str]
    remove_items: Optional[str]
    extra_notes: Optional[str]
    tariff: str
    status: str
    concept_text: Optional[str]
    shopping_list: Optional[dict]
    images: List[ProjectImageOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectSummary(BaseModel):
    id: int
    room_type: Optional[str]
    style: Optional[str]
    status: str
    tariff: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Payment schemas ──────────────────────────────────────────────────────────

class PaymentOut(BaseModel):
    id: int
    project_id: int
    tariff: str
    amount: int
    currency: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Generation job schemas ───────────────────────────────────────────────────

class GenerationJobOut(BaseModel):
    id: int
    project_id: int
    status: str
    attempts: int
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error_message: Optional[str]

    model_config = {"from_attributes": True}


# ─── Admin schemas ────────────────────────────────────────────────────────────

class StatsOut(BaseModel):
    total_users: int
    total_projects: int
    projects_done: int
    projects_failed: int
    projects_by_status: dict[str, int]


class BroadcastRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)
