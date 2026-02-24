"""add image_urls column to automation_tasks

Revision ID: add_image_urls_to_tasks
Revises: add_image_generation_cols
Create Date: 2026-01-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_image_urls_to_tasks'
down_revision = 'add_image_generation_cols'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text(
            "ALTER TABLE automation_tasks ADD COLUMN IF NOT EXISTS image_urls TEXT"
        ))
        print("✅ image_urls 컬럼 추가 완료")
    except Exception as e:
        print(f"ℹ️  image_urls 컬럼: {e}")


def downgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text("ALTER TABLE automation_tasks DROP COLUMN IF EXISTS image_urls"))
    except Exception as e:
        print(f"ℹ️  {e}")
