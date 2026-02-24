"""add draft_creation_schedules table

Revision ID: add_draft_creation_schedule
Revises: add_keyword_to_tasks
Create Date: 2026-01-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_draft_creation_schedule'
down_revision = 'add_keyword_to_tasks'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS draft_creation_schedules (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                post_title VARCHAR(500) DEFAULT '안녕하세요',
                post_body TEXT NOT NULL,
                cafes_per_account INTEGER DEFAULT 1,
                scheduled_hour INTEGER NOT NULL DEFAULT 9,
                scheduled_minute INTEGER NOT NULL DEFAULT 0,
                repeat_type VARCHAR(20) DEFAULT 'daily',
                repeat_days VARCHAR(100),
                target_pcs TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                last_run_at TIMESTAMP,
                next_run_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        print("✅ draft_creation_schedules 테이블 생성 완료")
    except Exception as e:
        print(f"ℹ️  draft_creation_schedules: {e}")


def downgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text("DROP TABLE IF EXISTS draft_creation_schedules"))
    except Exception as e:
        print(f"ℹ️  {e}")
