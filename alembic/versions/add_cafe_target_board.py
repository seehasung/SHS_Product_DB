"""add target_board to automation_cafes

Revision ID: add_cafe_target_board
Revises: add_ai_schedule_time_fields
Create Date: 2026-01-25
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_cafe_target_board'
down_revision = 'add_ai_schedule_time_fields'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text(
            "ALTER TABLE automation_cafes ADD COLUMN IF NOT EXISTS target_board VARCHAR(255)"
        ))
        print("✅ automation_cafes.target_board 컬럼 추가 완료")
    except Exception as e:
        print(f"ℹ️  target_board: {e}")


def downgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text(
            "ALTER TABLE automation_cafes DROP COLUMN IF EXISTS target_board"
        ))
    except Exception as e:
        print(f"ℹ️  drop target_board: {e}")
