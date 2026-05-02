"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name)


def upgrade() -> None:
    actor_type = _enum("actortype", "user", "admin", "system")
    room_type = _enum(
        "roomtype",
        "kitchen", "bedroom", "living", "kids",
        "bathroom", "office", "hallway", "other",
    )
    interior_style = _enum(
        "interiorstyle",
        "japandi", "minimalism", "modern", "scandinavian",
        "loft", "neoclassic", "cozy_light",
    )
    budget_tier = _enum(
        "budgettier", "minimal", "medium", "above_medium", "premium",
    )
    free_space = _enum("freespace", "30", "40", "50", "60")
    tariff = _enum(
        "tariff", "free", "room", "pro_room", "flat", "realtor_pack",
    )
    project_status = _enum(
        "projectstatus",
        "draft", "pending_confirmation", "pending_payment", "queued",
        "analyzing", "generating", "postprocessing",
        "done", "failed", "cancelled",
    )
    image_type = _enum("imagetype", "input", "output")
    payment_status = _enum(
        "paymentstatus", "pending", "succeeded", "failed", "refunded", "cancelled",
    )
    generation_job_status = _enum(
        "generationjobstatus", "pending", "running", "done", "failed",
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255)),
        sa.Column("first_name", sa.String(255)),
        sa.Column("last_name", sa.String(255)),
        sa.Column("language_code", sa.String(10)),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("free_previews_used", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("room_type", room_type),
        sa.Column("area_m2", sa.Float()),
        sa.Column("ceiling_height", sa.Float()),
        sa.Column("style", interior_style),
        sa.Column("budget_tier", budget_tier),
        sa.Column("free_space_percent", free_space),
        sa.Column("keep_items", sa.Text()),
        sa.Column("remove_items", sa.Text()),
        sa.Column("extra_notes", sa.Text()),
        sa.Column("tariff", tariff, nullable=False, server_default="free"),
        sa.Column("status", project_status, nullable=False, server_default="draft"),
        sa.Column("concept_text", sa.Text()),
        sa.Column("shopping_list", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])
    op.create_index("ix_projects_status", "projects", ["status"])

    op.create_table(
        "project_images",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("image_type", image_type, nullable=False),
        sa.Column("file_path", sa.String(1024)),
        sa.Column("file_id_telegram", sa.String(512)),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_project_images_project_id", "project_images", ["project_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="RUB"),
        sa.Column("status", payment_status, nullable=False, server_default="pending"),
        sa.Column("external_payment_id", sa.String(512)),
        sa.Column("tariff", tariff, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_payments_project_id", "payments", ["project_id"])
    op.create_index("ix_payments_user_id", "payments", ["user_id"])

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("status", generation_job_status, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_generation_jobs_project_id", "generation_jobs", ["project_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_type", actor_type, nullable=False),
        sa.Column("actor_id", sa.BigInteger()),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("entity_type", sa.String(64)),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("payload_json", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_index("ix_generation_jobs_project_id", table_name="generation_jobs")
    op.drop_table("generation_jobs")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_index("ix_payments_project_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_project_images_project_id", table_name="project_images")
    op.drop_table("project_images")
    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")

    for enum_name in (
        "generationjobstatus", "paymentstatus", "imagetype",
        "projectstatus", "tariff", "freespace",
        "budgettier", "interiorstyle", "roomtype", "actortype",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
