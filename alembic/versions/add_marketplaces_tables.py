"""add marketplaces and project_marketplaces tables

Revision ID: add_marketplaces_tables
Revises: add_projects_tables
Create Date: 2026-01-16 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_marketplaces_tables'
down_revision: Union[str, None] = 'add_projects_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if tables exist
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # Create marketplaces table if it doesn't exist
    if 'marketplaces' not in existing_tables:
        op.create_table(
            'marketplaces',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('code', sa.String(length=50), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='TRUE'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code')
        )
    
    # Create project_marketplaces table if it doesn't exist
    if 'project_marketplaces' not in existing_tables:
        op.create_table(
            'project_marketplaces',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('project_id', sa.Integer(), nullable=False),
            sa.Column('marketplace_id', sa.Integer(), nullable=False),
            sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='FALSE'),
            sa.Column('settings_json', postgresql.JSONB(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['marketplace_id'], ['marketplaces.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('project_id', 'marketplace_id', name='project_marketplaces_project_marketplace_unique')
        )
    
    # Create indexes if they don't exist
    if 'marketplaces' in existing_tables:
        existing_marketplace_indexes = [idx['name'] for idx in inspector.get_indexes('marketplaces')]
    else:
        existing_marketplace_indexes = []
    
    if 'idx_marketplaces_code' not in existing_marketplace_indexes:
        op.create_index('idx_marketplaces_code', 'marketplaces', ['code'])
    if 'idx_marketplaces_active' not in existing_marketplace_indexes:
        op.create_index('idx_marketplaces_active', 'marketplaces', ['is_active'])
    
    if 'project_marketplaces' in existing_tables:
        existing_pm_indexes = [idx['name'] for idx in inspector.get_indexes('project_marketplaces')]
    else:
        existing_pm_indexes = []
    
    if 'idx_project_marketplaces_project_id' not in existing_pm_indexes:
        op.create_index('idx_project_marketplaces_project_id', 'project_marketplaces', ['project_id'])
    if 'idx_project_marketplaces_marketplace_id' not in existing_pm_indexes:
        op.create_index('idx_project_marketplaces_marketplace_id', 'project_marketplaces', ['marketplace_id'])
    if 'idx_project_marketplaces_enabled' not in existing_pm_indexes:
        op.create_index('idx_project_marketplaces_enabled', 'project_marketplaces', ['is_enabled'])
    
    # Seed marketplaces
    op.execute("""
        INSERT INTO marketplaces (code, name, description, is_active)
        VALUES 
            ('wildberries', 'Wildberries', 'Крупнейший маркетплейс в России', TRUE),
            ('ozon', 'Ozon', 'Один из крупнейших маркетплейсов в России', TRUE),
            ('yandex_market', 'Яндекс.Маркет', 'Маркетплейс от Яндекса', TRUE),
            ('sbermegamarket', 'СберМегаМаркет', 'Маркетплейс от Сбера', TRUE)
        ON CONFLICT (code) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index('idx_project_marketplaces_enabled', table_name='project_marketplaces')
    op.drop_index('idx_project_marketplaces_marketplace_id', table_name='project_marketplaces')
    op.drop_index('idx_project_marketplaces_project_id', table_name='project_marketplaces')
    op.drop_index('idx_marketplaces_active', table_name='marketplaces')
    op.drop_index('idx_marketplaces_code', table_name='marketplaces')
    op.drop_table('project_marketplaces')
    op.drop_table('marketplaces')




