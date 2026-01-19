"""repair schema idempotency: ensure all columns/indexes/constraints exist

Revision ID: 71fcc51a5119
Revises: 670ed0736bfa
Create Date: 2026-01-16 20:00:00.000000

This repair migration ensures that all expected columns, indexes, and constraints
exist in the database, even if they were created manually or by code.
This makes the migration system idempotent and safe to run on databases with
schema drift.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = '71fcc51a5119'
down_revision: Union[str, None] = '670ed0736bfa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ensure all expected schema elements exist (idempotent repair)."""
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # Repair products table columns
    if 'products' in existing_tables:
        existing_columns = {col['name'] for col in inspector.get_columns('products')}
        existing_indexes = {idx['name'] for idx in inspector.get_indexes('products')}
        
        # Ensure all expected columns exist
        columns_to_ensure = [
            ('title', 'TEXT'),
            ('brand', 'TEXT'),
            ('subject_name', 'TEXT'),
            ('price_u', 'BIGINT'),
            ('sale_price_u', 'BIGINT'),
            ('rating', 'NUMERIC(3,2)'),
            ('feedbacks', 'INTEGER'),
            ('sizes', 'JSONB'),
            ('colors', 'JSONB'),
            ('pics', 'JSONB'),
            ('raw', 'JSONB'),
            ('updated_at', 'TIMESTAMPTZ DEFAULT now() NOT NULL'),
            ('first_seen_at', 'TIMESTAMPTZ DEFAULT now() NOT NULL'),
            ('subject_id', 'INTEGER'),
            ('description', 'TEXT'),
            ('dimensions', 'JSONB'),
            ('characteristics', 'JSONB'),
            ('created_at_api', 'TIMESTAMPTZ'),
            ('need_kiz', 'BOOLEAN'),
            ('project_id', 'INTEGER'),
        ]
        
        for col_name, col_type in columns_to_ensure:
            if col_name not in existing_columns:
                try:
                    op.execute(f"ALTER TABLE products ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                    print(f"Added missing column: products.{col_name}")
                except Exception as e:
                    print(f"Failed to add column products.{col_name}: {e}")
        
        # Ensure all expected indexes exist
        indexes_to_ensure = [
            ('idx_products_brand', 'products', ['brand']),
            ('idx_products_subject', 'products', ['subject_name']),
            ('idx_products_subject_id', 'products', ['subject_id']),
            ('idx_products_project_id', 'products', ['project_id']),
        ]
        
        for idx_name, table_name, columns in indexes_to_ensure:
            if idx_name not in existing_indexes:
                try:
                    cols_str = ', '.join(columns)
                    op.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({cols_str})")
                    print(f"Added missing index: {idx_name}")
                except Exception as e:
                    print(f"Failed to add index {idx_name}: {e}")
    
    # Repair price_snapshots table
    if 'price_snapshots' in existing_tables:
        existing_columns = {col['name'] for col in inspector.get_columns('price_snapshots')}
        existing_indexes = {idx['name'] for idx in inspector.get_indexes('price_snapshots')}
        
        if 'project_id' not in existing_columns:
            try:
                op.execute("ALTER TABLE price_snapshots ADD COLUMN IF NOT EXISTS project_id INTEGER")
                print("Added missing column: price_snapshots.project_id")
            except Exception as e:
                print(f"Failed to add column price_snapshots.project_id: {e}")
        
        if 'idx_price_snapshots_project_id' not in existing_indexes:
            try:
                op.execute("CREATE INDEX IF NOT EXISTS idx_price_snapshots_project_id ON price_snapshots (project_id)")
                print("Added missing index: idx_price_snapshots_project_id")
            except Exception as e:
                print(f"Failed to add index idx_price_snapshots_project_id: {e}")
    
    # Repair stock_snapshots table
    if 'stock_snapshots' in existing_tables:
        existing_columns = {col['name'] for col in inspector.get_columns('stock_snapshots')}
        existing_indexes = {idx['name'] for idx in inspector.get_indexes('stock_snapshots')}
        
        if 'project_id' not in existing_columns:
            try:
                op.execute("ALTER TABLE stock_snapshots ADD COLUMN IF NOT EXISTS project_id INTEGER")
                print("Added missing column: stock_snapshots.project_id")
            except Exception as e:
                print(f"Failed to add column stock_snapshots.project_id: {e}")
        
        if 'idx_stock_snapshots_project_id' not in existing_indexes:
            try:
                op.execute("CREATE INDEX IF NOT EXISTS idx_stock_snapshots_project_id ON stock_snapshots (project_id)")
                print("Added missing index: idx_stock_snapshots_project_id")
            except Exception as e:
                print(f"Failed to add index idx_stock_snapshots_project_id: {e}")
    
    # Repair project_marketplaces table (for api_token_encrypted)
    if 'project_marketplaces' in existing_tables:
        existing_columns = {col['name'] for col in inspector.get_columns('project_marketplaces')}
        
        if 'api_token_encrypted' not in existing_columns:
            try:
                op.execute("ALTER TABLE project_marketplaces ADD COLUMN IF NOT EXISTS api_token_encrypted TEXT")
                print("Added missing column: project_marketplaces.api_token_encrypted")
            except Exception as e:
                print(f"Failed to add column project_marketplaces.api_token_encrypted: {e}")
    
    print("Schema repair completed")


def downgrade() -> None:
    # Repair migration: no downgrade needed (columns/indexes can stay)
    pass


