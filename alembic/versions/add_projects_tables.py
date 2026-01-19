"""add projects and project_members tables

Revision ID: add_projects_tables
Revises: add_refresh_tokens
Create Date: 2026-01-16 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_projects_tables'
down_revision: Union[str, None] = 'add_refresh_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if tables exist
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # Create projects table if it doesn't exist
    if 'projects' not in existing_tables:
        op.create_table(
            'projects',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE')
        )
    
    # Create project_members table if it doesn't exist
    if 'project_members' not in existing_tables:
        op.create_table(
            'project_members',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('project_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('role', sa.String(length=20), nullable=False, server_default='member'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('project_id', 'user_id', name='project_members_project_user_unique')
        )
    
    # Create indexes if they don't exist
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('projects')] if 'projects' in existing_tables else []
    if 'idx_projects_created_by' not in existing_indexes:
        op.create_index('idx_projects_created_by', 'projects', ['created_by'])
    
    if 'project_members' in existing_tables:
        existing_member_indexes = [idx['name'] for idx in inspector.get_indexes('project_members')]
    else:
        existing_member_indexes = []
    
    if 'idx_project_members_project_id' not in existing_member_indexes:
        op.create_index('idx_project_members_project_id', 'project_members', ['project_id'])
    if 'idx_project_members_user_id' not in existing_member_indexes:
        op.create_index('idx_project_members_user_id', 'project_members', ['user_id'])
    if 'idx_project_members_role' not in existing_member_indexes:
        op.create_index('idx_project_members_role', 'project_members', ['role'])


def downgrade() -> None:
    op.drop_index('idx_project_members_role', table_name='project_members')
    op.drop_index('idx_project_members_user_id', table_name='project_members')
    op.drop_index('idx_project_members_project_id', table_name='project_members')
    op.drop_index('idx_projects_created_by', table_name='projects')
    op.drop_table('project_members')
    op.drop_table('projects')

