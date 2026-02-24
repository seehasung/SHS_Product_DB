"""add image generation columns to ai_prompts

Revision ID: add_image_generation_cols
Revises: add_automation_system_tables
Create Date: 2026-01-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_image_generation_cols'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    
    columns_to_add = [
        ("num_product_images", "ALTER TABLE ai_prompts ADD COLUMN IF NOT EXISTS num_product_images INTEGER DEFAULT 1"),
        ("num_attract_images", "ALTER TABLE ai_prompts ADD COLUMN IF NOT EXISTS num_attract_images INTEGER DEFAULT 2"),
        ("product_image_style", "ALTER TABLE ai_prompts ADD COLUMN IF NOT EXISTS product_image_style VARCHAR(100)"),
        ("attract_image_prompts", "ALTER TABLE ai_prompts ADD COLUMN IF NOT EXISTS attract_image_prompts TEXT"),
    ]
    
    for col_name, sql in columns_to_add:
        try:
            conn.execute(sa.text(sql))
            print(f"✅ 컬럼 추가: {col_name}")
        except Exception as e:
            print(f"ℹ️  컬럼 {col_name} 이미 존재하거나 오류: {e}")


def downgrade():
    conn = op.get_bind()
    for col in ["num_product_images", "num_attract_images", "product_image_style", "attract_image_prompts"]:
        try:
            conn.execute(sa.text(f"ALTER TABLE ai_prompts DROP COLUMN IF EXISTS {col}"))
        except Exception as e:
            print(f"ℹ️  {col} 제거 오류: {e}")
