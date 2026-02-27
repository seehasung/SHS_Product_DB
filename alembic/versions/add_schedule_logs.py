"""add schedule_logs table and cafe target_board

Revision ID: add_schedule_logs
Revises: add_cafe_target_board
Create Date: 2026-01-25
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_schedule_logs'
down_revision = 'add_cafe_target_board'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS schedule_logs (
                id SERIAL PRIMARY KEY,
                schedule_type VARCHAR(20) NOT NULL,
                schedule_id INTEGER NOT NULL,
                schedule_name VARCHAR(255),
                status VARCHAR(20) DEFAULT 'success',
                tasks_created INTEGER DEFAULT 0,
                message TEXT,
                executed_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_schedule_logs_schedule_id ON schedule_logs (schedule_id)"
        ))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_schedule_logs_executed_at ON schedule_logs (executed_at)"
        ))
        print("✅ schedule_logs 테이블 생성 완료")
    except Exception as e:
        print(f"ℹ️  schedule_logs: {e}")


def downgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text("DROP TABLE IF EXISTS schedule_logs"))
    except Exception as e:
        print(f"ℹ️  drop schedule_logs: {e}")
