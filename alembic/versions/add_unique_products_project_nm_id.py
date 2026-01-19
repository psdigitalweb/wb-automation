"""add unique constraint (project_id, nm_id) to products table

Revision ID: 946d21840243
Revises: backfill_project_id_not_null
Create Date: 2026-01-16 17:00:00.000000

This migration:
1. Drops the old UNIQUE constraint on nm_id (if exists)
2. Adds UNIQUE constraint on (project_id, nm_id) to allow same nm_id in different projects
3. Updates the index accordingly

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = '946d21840243'
down_revision: Union[str, None] = 'backfill_project_id_not_null'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if 'products' not in existing_tables:
        print("WARNING: products table does not exist, skipping unique constraint")
        return
    
    # Check if project_id column exists
    existing_columns = [col['name'] for col in inspector.get_columns('products')]
    if 'project_id' not in existing_columns:
        print("WARNING: project_id column does not exist in products, skipping unique constraint")
        return
    
    # Get existing constraints
    unique_constraints = inspector.get_unique_constraints('products')
    indexes = inspector.get_indexes('products')
    
    # 1. Drop old UNIQUE constraint on nm_id if it exists
    # Check for unique constraint on nm_id
    nm_id_unique = None
    for uc in unique_constraints:
        if len(uc['column_names']) == 1 and uc['column_names'][0] == 'nm_id':
            nm_id_unique = uc['name']
            break
    
    if nm_id_unique:
        # Drop the unique constraint (this will also drop the unique index)
        op.drop_constraint(nm_id_unique, 'products', type_='unique')
        print(f"Dropped old UNIQUE constraint on nm_id: {nm_id_unique}")
    
    # Also check for unique index on nm_id (might exist without named constraint)
    nm_id_unique_idx = None
    for idx in indexes:
        if idx.get('unique', False) and len(idx['column_names']) == 1 and idx['column_names'][0] == 'nm_id':
            nm_id_unique_idx = idx['name']
            break
    
    if nm_id_unique_idx and nm_id_unique_idx != nm_id_unique:
        # Drop the unique index
        op.drop_index(nm_id_unique_idx, table_name='products')
        print(f"Dropped old UNIQUE index on nm_id: {nm_id_unique_idx}")
    
    # 2. Create new UNIQUE constraint on (project_id, nm_id)
    # Check if constraint already exists
    project_nm_unique = None
    for uc in unique_constraints:
        if set(uc['column_names']) == {'project_id', 'nm_id'}:
            project_nm_unique = uc['name']
            break
    
    if not project_nm_unique:
        op.create_unique_constraint(
            'uq_products_project_nm_id',
            'products',
            ['project_id', 'nm_id']
        )
        print("Created UNIQUE constraint on (project_id, nm_id)")
    else:
        print(f"UNIQUE constraint on (project_id, nm_id) already exists: {project_nm_unique}")
    
    # 3. Ensure index exists for (project_id, nm_id) for performance
    # Check if index exists
    project_nm_idx = None
    for idx in indexes:
        if set(idx['column_names']) == {'project_id', 'nm_id'}:
            project_nm_idx = idx['name']
            break
    
    if not project_nm_idx:
        op.create_index(
            'idx_products_project_nm_id',
            'products',
            ['project_id', 'nm_id']
        )
        print("Created index on (project_id, nm_id)")
    else:
        print(f"Index on (project_id, nm_id) already exists: {project_nm_idx}")
    
    # 4. Keep individual index on nm_id for queries that filter by nm_id only
    nm_id_idx = None
    for idx in indexes:
        if not idx.get('unique', False) and len(idx['column_names']) == 1 and idx['column_names'][0] == 'nm_id':
            nm_id_idx = idx['name']
            break
    
    if not nm_id_idx:
        op.create_index('idx_products_nm_id', 'products', ['nm_id'])
        print("Created non-unique index on nm_id")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if 'products' not in existing_tables:
        return
    
    # Drop the composite unique constraint
    unique_constraints = inspector.get_unique_constraints('products')
    for uc in unique_constraints:
        if set(uc['column_names']) == {'project_id', 'nm_id'}:
            op.drop_constraint(uc['name'], 'products', type_='unique')
            print(f"Dropped UNIQUE constraint: {uc['name']}")
    
    # Drop the composite index
    indexes = inspector.get_indexes('products')
    for idx in indexes:
        if set(idx['column_names']) == {'project_id', 'nm_id'}:
            op.drop_index(idx['name'], table_name='products')
            print(f"Dropped index: {idx['name']}")
    
    # Restore old UNIQUE constraint on nm_id (if needed)
    # Note: This might fail if there are duplicate nm_id values across projects
    # In that case, the user needs to manually resolve duplicates first
    try:
        op.create_unique_constraint(
            'uq_products_nm_id',
            'products',
            ['nm_id']
        )
        print("Restored UNIQUE constraint on nm_id")
    except Exception as e:
        print(f"WARNING: Could not restore UNIQUE constraint on nm_id: {e}")
        print("You may need to resolve duplicate nm_id values first")

