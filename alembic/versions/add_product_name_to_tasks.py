"""add product_name column to automation_tasks

Revision ID: add_product_name_to_tasks
Revises: add_keyword_to_tasks
Create Date: 2026-01-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_product_name_to_tasks'
down_revision = 'add_schedule_logs'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text(
            "ALTER TABLE automation_tasks ADD COLUMN IF NOT EXISTS product_name VARCHAR(500)"
        ))
        print("✅ product_name 컬럼 추가 완료")
    except Exception as e:
        print(f"ℹ️  product_name 컬럼: {e}")


def downgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text("ALTER TABLE automation_tasks DROP COLUMN IF EXISTS product_name"))
    except Exception as e:
        print(f"ℹ️  {e}")
