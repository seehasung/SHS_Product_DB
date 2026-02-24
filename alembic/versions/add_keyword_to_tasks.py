"""add keyword column to automation_tasks

Revision ID: add_keyword_to_tasks
Revises: add_image_urls_to_tasks
Create Date: 2026-01-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_keyword_to_tasks'
down_revision = 'add_image_urls_to_tasks'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text(
            "ALTER TABLE automation_tasks ADD COLUMN IF NOT EXISTS keyword VARCHAR(255)"
        ))
        print("✅ keyword 컬럼 추가 완료")
    except Exception as e:
        print(f"ℹ️  keyword 컬럼: {e}")


def downgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text("ALTER TABLE automation_tasks DROP COLUMN IF EXISTS keyword"))
    except Exception as e:
        print(f"ℹ️  {e}")
