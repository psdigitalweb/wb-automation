"""add api_token_encrypted field to project_marketplaces

Revision ID: e373f63d276a
Revises: 946d21840243
Create Date: 2026-01-16 18:00:00.000000

This migration:
1. Adds api_token_encrypted TEXT column to project_marketplaces
2. Migrates existing tokens from settings_json to api_token_encrypted (if encryption available)
3. Removes api_token/token from settings_json for existing rows

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text, inspect


# revision identifiers, used by Alembic.
revision: str = 'e373f63d276a'
down_revision: Union[str, None] = '946d21840243'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if 'project_marketplaces' not in existing_tables:
        print("WARNING: project_marketplaces table does not exist, skipping migration")
        return
    
    # Check if column already exists
    existing_columns = [col['name'] for col in inspector.get_columns('project_marketplaces')]
    if 'api_token_encrypted' in existing_columns:
        print("api_token_encrypted column already exists, skipping")
        return
    
    # 1. Add api_token_encrypted column
    op.add_column('project_marketplaces', sa.Column('api_token_encrypted', sa.Text(), nullable=True))
    print("Added api_token_encrypted column to project_marketplaces")
    
    # 2. Migrate existing tokens from settings_json to api_token_encrypted
    # Only if encryption is available (PROJECT_SECRETS_KEY is set)
    try:
        import os
        if os.getenv("PROJECT_SECRETS_KEY"):
            from app.utils.secrets_encryption import encrypt_token
            
            # Get all rows with settings_json containing tokens
            select_sql = text("""
                SELECT id, settings_json
                FROM project_marketplaces
                WHERE settings_json IS NOT NULL
            """)
            
            result = conn.execute(select_sql).mappings().all()
            migrated_count = 0
            
            for row in result:
                pm_id = row['id']
                settings = row['settings_json']
                
                if not settings:
                    continue
                
                # Parse settings_json
                if isinstance(settings, str):
                    import json
                    try:
                        settings = json.loads(settings)
                    except:
                        continue
                
                # Extract token
                token = settings.get("api_token") or settings.get("token")
                if not token or token == "***" or token.upper() == "MOCK":
                    continue
                
                # Encrypt and save
                try:
                    encrypted_token = encrypt_token(token)
                    update_sql = text("""
                        UPDATE project_marketplaces
                        SET api_token_encrypted = :encrypted_token
                        WHERE id = :pm_id
                    """)
                    conn.execute(update_sql, {"encrypted_token": encrypted_token, "pm_id": pm_id})
                    
                    # Remove token from settings_json
                    settings_clean = {k: v for k, v in settings.items() if k not in ("api_token", "token")}
                    settings_clean_json = json.dumps(settings_clean) if settings_clean else None
                    
                    update_settings_sql = text("""
                        UPDATE project_marketplaces
                        SET settings_json = CAST(:settings_json AS jsonb)
                        WHERE id = :pm_id
                    """)
                    conn.execute(update_settings_sql, {"settings_json": settings_clean_json, "pm_id": pm_id})
                    
                    migrated_count += 1
                except Exception as e:
                    print(f"WARNING: Failed to migrate token for project_marketplace id={pm_id}: {e}")
            
            if migrated_count > 0:
                print(f"Migrated {migrated_count} tokens from settings_json to api_token_encrypted")
            else:
                print("No tokens found in settings_json to migrate")
        else:
            print("PROJECT_SECRETS_KEY not set, skipping token migration (tokens will be encrypted on next connect)")
    except Exception as e:
        print(f"WARNING: Failed to migrate existing tokens: {e}")
        print("Tokens will be encrypted on next connect")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if 'project_marketplaces' not in existing_tables:
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('project_marketplaces')]
    if 'api_token_encrypted' not in existing_columns:
        return
    
    # Note: We don't decrypt and move back to settings_json in downgrade
    # as it's a security risk. The column is just dropped.
    op.drop_column('project_marketplaces', 'api_token_encrypted')
    print("Dropped api_token_encrypted column from project_marketplaces")

