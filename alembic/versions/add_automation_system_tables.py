"""Add automation system tables

Revision ID: a1b2c3d4e5f6
Revises: 56c4f9015f59
Create Date: 2025-12-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '56c4f9015f59'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    
    # 1. automation_worker_pcs
    op.create_table(
        'automation_worker_pcs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pc_number', sa.Integer(), nullable=False),
        sa.Column('pc_name', sa.String(length=100), nullable=False),
        sa.Column('ip_address', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('current_task_id', sa.Integer(), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=True),
        sa.Column('cpu_usage', sa.Float(), nullable=True),
        sa.Column('memory_usage', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_automation_worker_pcs_id'), 'automation_worker_pcs', ['id'], unique=False)
    op.create_index(op.f('ix_automation_worker_pcs_pc_number'), 'automation_worker_pcs', ['pc_number'], unique=True)
    
    # 2. automation_accounts
    op.create_table(
        'automation_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.String(length=100), nullable=False),
        sa.Column('account_pw', sa.String(length=255), nullable=False),
        sa.Column('assigned_pc_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('login_status', sa.String(length=20), nullable=True),
        sa.Column('total_posts', sa.Integer(), nullable=True),
        sa.Column('total_comments', sa.Integer(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_pc_id'], ['automation_worker_pcs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_automation_accounts_account_id'), 'automation_accounts', ['account_id'], unique=True)
    op.create_index(op.f('ix_automation_accounts_id'), 'automation_accounts', ['id'], unique=False)
    
    # 3. automation_cafes
    op.create_table(
        'automation_cafes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('cafe_id', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_automation_cafes_id'), 'automation_cafes', ['id'], unique=False)
    op.create_index(op.f('ix_automation_cafes_url'), 'automation_cafes', ['url'], unique=True)
    
    # 4. automation_prompts
    op.create_table(
        'automation_prompts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('prompt_type', sa.String(length=50), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('user_prompt_template', sa.Text(), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('max_tokens', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_automation_prompts_id'), 'automation_prompts', ['id'], unique=False)
    
    # 5. automation_schedules
    op.create_table(
        'automation_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('scheduled_date', sa.Date(), nullable=False),
        sa.Column('marketing_product_id', sa.Integer(), nullable=True),
        sa.Column('keyword_text', sa.String(length=255), nullable=False),
        sa.Column('marketing_post_id', sa.Integer(), nullable=True),
        sa.Column('prompt_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('is_completed', sa.Boolean(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['marketing_post_id'], ['marketing_posts.id'], ),
        sa.ForeignKeyConstraint(['marketing_product_id'], ['marketing_products.id'], ),
        sa.ForeignKeyConstraint(['prompt_id'], ['automation_prompts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_automation_schedules_id'), 'automation_schedules', ['id'], unique=False)
    op.create_index(op.f('ix_automation_schedules_scheduled_date'), 'automation_schedules', ['scheduled_date'], unique=False)
    
    # 6. automation_tasks
    op.create_table(
        'automation_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_type', sa.String(length=20), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('schedule_id', sa.Integer(), nullable=True),
        sa.Column('scheduled_time', sa.DateTime(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('parent_task_id', sa.Integer(), nullable=True),
        sa.Column('order_sequence', sa.Integer(), nullable=True),
        sa.Column('assigned_pc_id', sa.Integer(), nullable=True),
        sa.Column('assigned_account_id', sa.Integer(), nullable=True),
        sa.Column('cafe_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('post_url', sa.String(length=500), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_account_id'], ['automation_accounts.id'], ),
        sa.ForeignKeyConstraint(['assigned_pc_id'], ['automation_worker_pcs.id'], ),
        sa.ForeignKeyConstraint(['cafe_id'], ['automation_cafes.id'], ),
        sa.ForeignKeyConstraint(['parent_task_id'], ['automation_tasks.id'], ),
        sa.ForeignKeyConstraint(['schedule_id'], ['automation_schedules.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_automation_tasks_id'), 'automation_tasks', ['id'], unique=False)
    op.create_index(op.f('ix_automation_tasks_scheduled_time'), 'automation_tasks', ['scheduled_time'], unique=False)
    op.create_index(op.f('ix_automation_tasks_status'), 'automation_tasks', ['status'], unique=False)
    
    # 7. automation_posts
    op.create_table(
        'automation_posts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('post_url', sa.String(length=500), nullable=True),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('cafe_id', sa.Integer(), nullable=True),
        sa.Column('marketing_product_id', sa.Integer(), nullable=True),
        sa.Column('keyword_text', sa.String(length=255), nullable=True),
        sa.Column('view_count', sa.Integer(), nullable=True),
        sa.Column('comment_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['automation_accounts.id'], ),
        sa.ForeignKeyConstraint(['cafe_id'], ['automation_cafes.id'], ),
        sa.ForeignKeyConstraint(['marketing_product_id'], ['marketing_products.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_automation_posts_id'), 'automation_posts', ['id'], unique=False)
    
    # 8. automation_comments
    op.create_table(
        'automation_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=True),
        sa.Column('parent_comment_id', sa.Integer(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('order_sequence', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['automation_accounts.id'], ),
        sa.ForeignKeyConstraint(['parent_comment_id'], ['automation_comments.id'], ),
        sa.ForeignKeyConstraint(['post_id'], ['automation_posts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_automation_comments_id'), 'automation_comments', ['id'], unique=False)
    
    # current_task_id 외래키 추가 (순환 참조 방지를 위해 마지막에)
    op.create_foreign_key(
        'fk_automation_worker_pcs_current_task',
        'automation_worker_pcs',
        'automation_tasks',
        ['current_task_id'],
        ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    
    # 역순으로 삭제
    op.drop_constraint('fk_automation_worker_pcs_current_task', 'automation_worker_pcs', type_='foreignkey')
    
    op.drop_index(op.f('ix_automation_comments_id'), table_name='automation_comments')
    op.drop_table('automation_comments')
    
    op.drop_index(op.f('ix_automation_posts_id'), table_name='automation_posts')
    op.drop_table('automation_posts')
    
    op.drop_index(op.f('ix_automation_tasks_status'), table_name='automation_tasks')
    op.drop_index(op.f('ix_automation_tasks_scheduled_time'), table_name='automation_tasks')
    op.drop_index(op.f('ix_automation_tasks_id'), table_name='automation_tasks')
    op.drop_table('automation_tasks')
    
    op.drop_index(op.f('ix_automation_schedules_scheduled_date'), table_name='automation_schedules')
    op.drop_index(op.f('ix_automation_schedules_id'), table_name='automation_schedules')
    op.drop_table('automation_schedules')
    
    op.drop_index(op.f('ix_automation_prompts_id'), table_name='automation_prompts')
    op.drop_table('automation_prompts')
    
    op.drop_index(op.f('ix_automation_cafes_url'), table_name='automation_cafes')
    op.drop_index(op.f('ix_automation_cafes_id'), table_name='automation_cafes')
    op.drop_table('automation_cafes')
    
    op.drop_index(op.f('ix_automation_accounts_id'), table_name='automation_accounts')
    op.drop_index(op.f('ix_automation_accounts_account_id'), table_name='automation_accounts')
    op.drop_table('automation_accounts')
    
    op.drop_index(op.f('ix_automation_worker_pcs_pc_number'), table_name='automation_worker_pcs')
    op.drop_index(op.f('ix_automation_worker_pcs_id'), table_name='automation_worker_pcs')
    op.drop_table('automation_worker_pcs')

