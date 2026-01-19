"""add users table for authentication

Revision ID: add_users_table
Revises: add_product_details
Create Date: 2026-01-16 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_users_table'
down_revision: Union[str, None] = 'add_product_details'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table exists before creating (idempotent migration)
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # Create users table if it doesn't exist
    if 'users' not in existing_tables:
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('username', sa.String(length=64), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=True),
            sa.Column('hashed_password', sa.String(length=255), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='TRUE'),
            sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default='FALSE'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('username'),
            sa.UniqueConstraint('email')
        )
    else:
        print("Table users already exists, skipping creation")
    
    # Create indexes if they don't exist (for existing table or newly created)
    # Refresh inspector after potentially creating table
    if 'users' in inspector.get_table_names():
        existing_indexes = [idx['name'] for idx in inspector.get_indexes('users')]
        if 'idx_users_username' not in existing_indexes:
            op.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users (username)")
        if 'idx_users_email' not in existing_indexes:
            op.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)")


def downgrade() -> None:
    op.drop_index('idx_users_email', table_name='users')
    op.drop_index('idx_users_username', table_name='users')
    op.drop_table('users')

