"""Pytest fixtures shared across the test suite.

Sets sane defaults for environment variables that ``Settings`` requires at
import time so that pure unit tests don't blow up on missing secrets.
"""
import os

# These must be set before any module that imports ``app.core.config`` is
# collected, so we mutate ``os.environ`` at module import.
os.environ.setdefault("BOT_TOKEN", "test:fake-token")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AI_API_KEY", "test")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")
os.environ.setdefault("PAYMENT_TOKEN", "test")
