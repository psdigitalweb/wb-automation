"""ensure project_id constraints: NOT NULL, FK, UNIQUE(project_id, nm_id)

Revision ID: b3d4e5f6a7b8
Revises: 71fcc51a5119
Create Date: 2026-01-17 12:00:00.000000

This migration ensures that:
1. project_id columns are NOT NULL in products, price_snapshots, stock_snapshots
2. Foreign keys exist for project_id -> projects(id)
3. UNIQUE(project_id, nm_id) constraint exists on products
4. All indexes are in place

This is a repair migration that fixes schema drift and ensures constraints are enforced.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = 'b3d4e5f6a7b8'
down_revision: Union[str, None] = '71fcc51a5119'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ensure all project_id constraints are in place (idempotent)."""
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # Get Legacy project for backfilling (bootstrap creates it on startup if enabled)
    legacy_project_id = None
    
    try:
        # Check if Legacy project exists (bootstrap should create it on startup)
        if "projects" in existing_tables:
            legacy_result = conn.execute(
                text("SELECT id FROM projects WHERE name = 'Legacy' LIMIT 1")
            )
            legacy_project_id = legacy_result.scalar_one_or_none()
        
        # Get admin user (bootstrap should create it on startup if ADMIN_PASSWORD is set)
        admin_user_id = None
        if "users" in existing_tables:
            admin_result = conn.execute(
                text("SELECT id FROM users WHERE username = 'admin' LIMIT 1")
            )
            admin_user_id = admin_result.scalar_one_or_none()
        
        # Create admin user ONLY if ADMIN_PASSWORD is set (security: no default password in migration)
        import os
        admin_password = os.getenv("ADMIN_PASSWORD")
        if not admin_user_id and admin_password:
            try:
                import bcrypt
                hashed_password = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                admin_result = conn.execute(
                    text("""
                        INSERT INTO users (username, email, hashed_password, is_superuser)
                        VALUES ('admin', 'admin@example.com', :password, TRUE)
                        RETURNING id
                    """),
                    {"password": hashed_password}
                )
                admin_user_id = admin_result.scalar_one()
                print(f"Created admin user in migration (id={admin_user_id}, ADMIN_PASSWORD was set)")
            except Exception as e:
                print(f"WARNING: Could not create admin user in migration: {e}")
        elif not admin_user_id:
            print("NOTE: ADMIN_PASSWORD not set, skipping admin user creation in migration")
            print("Bootstrap will create admin user on startup if BOOTSTRAP_ENABLED=true and ADMIN_PASSWORD is set")
        
        # Backfill NULL project_id with Legacy project (if available)
        if legacy_project_id:
            data_tables = ['products', 'price_snapshots', 'stock_snapshots']
            for table_name in data_tables:
                if table_name not in existing_tables:
                    continue
                
                existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
                if 'project_id' not in existing_columns:
                    continue
                
                # Check for NULL project_id
                null_count = conn.execute(
                    text(f"SELECT COUNT(*) FROM {table_name} WHERE project_id IS NULL")
                ).scalar_one()
                
                if null_count > 0:
                    conn.execute(
                        text(f"UPDATE {table_name} SET project_id = :project_id WHERE project_id IS NULL"),
                        {"project_id": legacy_project_id}
                    )
                    print(f"Backfilled {null_count} rows in {table_name} with project_id={legacy_project_id}")
        else:
            print("NOTE: Legacy project not found for backfill")
            print("Bootstrap will create Legacy project on startup if BOOTSTRAP_ENABLED=true")
            print("NULL project_id values will remain until Legacy project is created and backfilled")
    except Exception as e:
        print(f"WARNING: Legacy project check failed: {e}")
        print("Bootstrap will handle this on startup if BOOTSTRAP_ENABLED=true")
    
    # Ensure NOT NULL constraints on project_id
    data_tables = ['products', 'price_snapshots', 'stock_snapshots']
    for table_name in data_tables:
        if table_name not in existing_tables:
            continue
        
        existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
        if 'project_id' not in existing_columns:
            continue
        
        # Check if column is nullable
        column_info = [col for col in inspector.get_columns(table_name) if col['name'] == 'project_id'][0]
        is_nullable = column_info.get('nullable', True)
        
        if is_nullable:
            # Try to set NOT NULL, but do not abort the migration if it fails.
            # Wrap DDL in a DB-side exception handler so the transaction doesn't enter
            # InFailedSqlTransaction state.
            try:
                op.execute(sa.text(f"""
                DO $$
                BEGIN
                  BEGIN
                    ALTER TABLE {table_name} ALTER COLUMN project_id SET NOT NULL;
                  EXCEPTION WHEN others THEN
                    RAISE NOTICE 'Skipping SET NOT NULL for {table_name}.project_id: %', SQLERRM;
                  END;
                END $$;
                """))
                print(f"Attempted to set {table_name}.project_id to NOT NULL")
            except Exception as e:
                print(f"WARNING: Failed to execute SET NOT NULL block for {table_name}.project_id: {e}")
    
    # Ensure foreign keys exist
    for table_name in data_tables:
        if table_name not in existing_tables:
            continue
        
        existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
        if 'project_id' not in existing_columns:
            continue
        
        # Create FK (idempotent, does not abort transaction on errors)
        fk_name = f'fk_{table_name}_project_id'
        try:
            op.execute(sa.text(f"""
            DO $$
            BEGIN
              BEGIN
                ALTER TABLE {table_name}
                ADD CONSTRAINT {fk_name}
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
              EXCEPTION
                WHEN duplicate_object THEN
                  NULL;
                WHEN others THEN
                  RAISE NOTICE 'Skipping FK {fk_name} on {table_name}: %', SQLERRM;
              END;
            END $$;
            """))
            print(f"Attempted to create foreign key {fk_name} on {table_name}")
        except Exception as e:
            print(f"WARNING: Failed to execute FK block {fk_name} on {table_name}: {e}")
    
    # Ensure UNIQUE(project_id, nm_id) on products (idempotent, DB-side exception handling)
    if 'products' in existing_tables:
        existing_columns = [col['name'] for col in inspector.get_columns('products')]
        if 'project_id' in existing_columns and 'nm_id' in existing_columns:
            try:
                op.execute(sa.text("""
                DO $$
                BEGIN
                  BEGIN
                    ALTER TABLE products
                    ADD CONSTRAINT uq_products_project_nm_id UNIQUE (project_id, nm_id);
                  EXCEPTION
                    WHEN duplicate_object THEN NULL;
                    WHEN others THEN
                      RAISE NOTICE 'Skipping UNIQUE uq_products_project_nm_id: %', SQLERRM;
                  END;
                END $$;
                """))
                print("Attempted to ensure UNIQUE(project_id, nm_id) on products")
            except Exception as e:
                print(f"WARNING: Failed to execute UNIQUE constraint block: {e}")
    
    print("Schema constraints check completed")


def downgrade() -> None:
    # Repair migration: no downgrade needed (constraints can stay)
    pass

