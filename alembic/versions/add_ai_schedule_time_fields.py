"""add ai schedule time fields

Revision ID: add_ai_schedule_time_fields
Revises: add_draft_creation_schedule
Create Date: 2026-01-24
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_ai_schedule_time_fields'
down_revision = 'add_draft_creation_schedule'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    columns = [
        ("scheduled_hour",    "INTEGER DEFAULT 9"),
        ("scheduled_minute",  "INTEGER DEFAULT 0"),
        ("repeat_type",       "VARCHAR(20) DEFAULT 'daily'"),
        ("repeat_days",       "VARCHAR(100)"),
        ("posts_per_account", "INTEGER DEFAULT 1"),
        ("last_run_at",       "TIMESTAMP"),
        ("next_run_at",       "TIMESTAMP"),
        ("is_active",         "BOOLEAN DEFAULT TRUE"),
    ]
    for col_name, col_def in columns:
        try:
            conn.execute(sa.text(
                f"ALTER TABLE ai_marketing_schedules ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
            ))
            print(f"✅ ai_marketing_schedules.{col_name} 추가 완료")
        except Exception as e:
            print(f"ℹ️  {col_name}: {e}")


def downgrade():
    conn = op.get_bind()
    for col_name in [
        "scheduled_hour", "scheduled_minute", "repeat_type",
        "repeat_days", "posts_per_account", "last_run_at",
        "next_run_at", "is_active"
    ]:
        try:
            conn.execute(sa.text(
                f"ALTER TABLE ai_marketing_schedules DROP COLUMN IF EXISTS {col_name}"
            ))
        except Exception as e:
            print(f"ℹ️  drop {col_name}: {e}")
