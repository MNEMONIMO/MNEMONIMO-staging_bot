from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    BigInteger, String, Integer, Float, Boolean, Text,
    DateTime, ForeignKey, Enum as SAEnum, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.db.session import Base


# ─── Enums ────────────────────────────────────────────────────────────────────

class RoomType(str, enum.Enum):
    KITCHEN = "kitchen"
    BEDROOM = "bedroom"
    LIVING = "living"
    KIDS = "kids"
    BATHROOM = "bathroom"
    OFFICE = "office"
    HALLWAY = "hallway"
    OTHER = "other"


class InteriorStyle(str, enum.Enum):
    JAPANDI = "japandi"
    MINIMALISM = "minimalism"
    MODERN = "modern"
    SCANDINAVIAN = "scandinavian"
    LOFT = "loft"
    NEOCLASSIC = "neoclassic"
    COZY_LIGHT = "cozy_light"


class BudgetTier(str, enum.Enum):
    MINIMAL = "minimal"
    MEDIUM = "medium"
    ABOVE_MEDIUM = "above_medium"
    PREMIUM = "premium"


class FreeSpace(str, enum.Enum):
    S30 = "30"
    S40 = "40"
    S50 = "50"
    S60 = "60"


class Tariff(str, enum.Enum):
    FREE = "free"
    ROOM = "room"
    PRO_ROOM = "pro_room"
    FLAT = "flat"
    REALTOR_PACK = "realtor_pack"


class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_CONFIRMATION = "pending_confirmation"
    PENDING_PAYMENT = "pending_payment"
    QUEUED = "queued"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    POSTPROCESSING = "postprocessing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImageType(str, enum.Enum):
    INPUT = "input"
    OUTPUT = "output"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class GenerationJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ActorType(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


# ─── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    free_previews_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    projects: Mapped[List["Project"]] = relationship("Project", back_populates="user")
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id} tg_id={self.telegram_id} username={self.username}>"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Room parameters
    room_type: Mapped[Optional[str]] = mapped_column(SAEnum(RoomType), nullable=True)
    area_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ceiling_height: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    style: Mapped[Optional[str]] = mapped_column(SAEnum(InteriorStyle), nullable=True)
    budget_tier: Mapped[Optional[str]] = mapped_column(SAEnum(BudgetTier), nullable=True)
    free_space_percent: Mapped[Optional[str]] = mapped_column(SAEnum(FreeSpace), nullable=True)
    keep_items: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remove_items: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    tariff: Mapped[str] = mapped_column(SAEnum(Tariff), default=Tariff.FREE)
    status: Mapped[str] = mapped_column(
        SAEnum(ProjectStatus), default=ProjectStatus.DRAFT, index=True
    )
    concept_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    shopping_list: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="projects")
    images: Mapped[List["ProjectImage"]] = relationship(
        "ProjectImage", back_populates="project", cascade="all, delete-orphan"
    )
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="project")
    generation_jobs: Mapped[List["GenerationJob"]] = relationship(
        "GenerationJob", back_populates="project", cascade="all, delete-orphan"
    )

    @property
    def input_photos(self) -> List["ProjectImage"]:
        return [img for img in self.images if img.image_type == ImageType.INPUT]

    @property
    def output_images(self) -> List["ProjectImage"]:
        return [img for img in self.images if img.image_type == ImageType.OUTPUT]

    def __repr__(self) -> str:
        return f"<Project id={self.id} user_id={self.user_id} status={self.status}>"


class ProjectImage(Base):
    __tablename__ = "project_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False, index=True
    )
    image_type: Mapped[str] = mapped_column(SAEnum(ImageType), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    file_id_telegram: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="images")

    def __repr__(self) -> str:
        return f"<ProjectImage id={self.id} project_id={self.project_id} type={self.image_type}>"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    status: Mapped[str] = mapped_column(SAEnum(PaymentStatus), default=PaymentStatus.PENDING)
    external_payment_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    tariff: Mapped[str] = mapped_column(SAEnum(Tariff), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project"] = relationship("Project", back_populates="payments")
    user: Mapped["User"] = relationship("User", back_populates="payments")

    def __repr__(self) -> str:
        return f"<Payment id={self.id} amount={self.amount} status={self.status}>"


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        SAEnum(GenerationJobStatus), default=GenerationJobStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="generation_jobs")

    def __repr__(self) -> str:
        return f"<GenerationJob id={self.id} project_id={self.project_id} status={self.status}>"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_type: Mapped[str] = mapped_column(SAEnum(ActorType), nullable=False)
    actor_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action} actor={self.actor_type}:{self.actor_id}>"
