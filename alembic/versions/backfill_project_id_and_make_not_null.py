"""backfill project_id for existing data and make it NOT NULL

Revision ID: backfill_project_id_not_null
Revises: add_project_id_to_data
Create Date: 2026-01-16 16:00:00.000000

This migration:
1. Backfills project_id for existing rows:
   - If there's exactly one project: assign all data to it
   - If multiple projects or none: create "Legacy" project and assign all data to it
2. Makes project_id NOT NULL (after backfill ensures all rows have project_id)

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text, inspect


# revision identifiers, used by Alembic.
revision: str = 'backfill_project_id_not_null'
down_revision: Union[str, None] = 'add_project_id_to_data'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # Check if projects table exists
    if 'projects' not in existing_tables:
        print("WARNING: projects table does not exist, skipping backfill")
        return
    
    # 1. Get project count
    project_count_sql = text("SELECT COUNT(*) FROM projects")
    project_count = conn.execute(project_count_sql).scalar_one()
    
    target_project_id = None
    
    if project_count == 1:
        # Single project: assign all data to it
        get_project_sql = text("SELECT id FROM projects LIMIT 1")
        target_project_id = conn.execute(get_project_sql).scalar_one()
        print(f"Found single project (id={target_project_id}), assigning all data to it")
    else:
        # Multiple projects or none: create "Legacy" project
        print(f"Found {project_count} projects, creating Legacy project for existing data")
        
        # Get first user as creator (or use NULL if no users)
        get_user_sql = text("SELECT id FROM users LIMIT 1")
        first_user = conn.execute(get_user_sql).scalar_one_or_none()
        
        if first_user is None:
            print("WARNING: No users found, cannot create Legacy project. Setting project_id to NULL for now.")
            print("You may need to create a project manually and update the data.")
        else:
            # Create Legacy project
            create_legacy_project_sql = text("""
                INSERT INTO projects (name, description, created_by)
                VALUES ('Legacy', 'Legacy project for data created before project scoping', :created_by)
                RETURNING id
            """)
            result = conn.execute(create_legacy_project_sql, {"created_by": first_user})
            target_project_id = result.scalar_one()
            
            # Add creator as owner
            add_owner_sql = text("""
                INSERT INTO project_members (project_id, user_id, role)
                VALUES (:project_id, :user_id, 'owner')
                ON CONFLICT (project_id, user_id) DO NOTHING
            """)
            conn.execute(add_owner_sql, {"project_id": target_project_id, "user_id": first_user})
            
            print(f"Created Legacy project (id={target_project_id})")
    
    # 2. Backfill project_id for each table (if target_project_id is available)
    if target_project_id is not None:
        tables_to_backfill = [
            ("products", "project_id"),
            ("stock_snapshots", "project_id"),
            ("price_snapshots", "project_id"),
        ]
        
        for table_name, column_name in tables_to_backfill:
            if table_name not in existing_tables:
                print(f"Skipping {table_name} - table does not exist")
                continue
            
            # Check if column exists
            existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
            if column_name not in existing_columns:
                print(f"Skipping {table_name}.{column_name} - column does not exist")
                continue
            
            # Count rows with NULL project_id
            count_null_sql = text(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} IS NULL")
            null_count = conn.execute(count_null_sql).scalar_one()
            
            if null_count > 0:
                # Update NULL project_id to target_project_id
                update_sql = text(f"""
                    UPDATE {table_name}
                    SET {column_name} = :project_id
                    WHERE {column_name} IS NULL
                """)
                conn.execute(update_sql, {"project_id": target_project_id})
                print(f"Backfilled {null_count} rows in {table_name} with project_id={target_project_id}")
            else:
                print(f"No NULL project_id found in {table_name}")
        
        # 3. Make project_id NOT NULL (only if we have target_project_id)
        # Note: PostgreSQL requires ALTER COLUMN ... SET NOT NULL, but we need to ensure no NULLs exist first
        for table_name, column_name in tables_to_backfill:
            if table_name not in existing_tables:
                continue
            
            existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
            if column_name not in existing_columns:
                continue
            
            # Check if column is already NOT NULL
            column_info = [col for col in inspector.get_columns(table_name) if col['name'] == column_name]
            if column_info and column_info[0].get('nullable', True) == False:
                print(f"{table_name}.{column_name} is already NOT NULL")
                continue
            
            # Verify no NULLs exist (safety check)
            count_null_sql = text(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} IS NULL")
            null_count = conn.execute(count_null_sql).scalar_one()
            
            if null_count == 0:
                # Set NOT NULL
                op.alter_column(table_name, column_name, nullable=False)
                print(f"Set {table_name}.{column_name} to NOT NULL")
            else:
                print(f"WARNING: {null_count} NULL values still exist in {table_name}.{column_name}, skipping NOT NULL constraint")
    else:
        print("WARNING: No target project available, skipping backfill and NOT NULL constraint")
        print("You may need to manually update data and rerun this migration")


def downgrade() -> None:
    # Revert NOT NULL constraints (make nullable again)
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    tables_to_revert = [
        ("products", "project_id"),
        ("stock_snapshots", "project_id"),
        ("price_snapshots", "project_id"),
    ]
    
    for table_name, column_name in tables_to_revert:
        if table_name not in existing_tables:
            continue
        
        existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
        if column_name not in existing_columns:
            continue
        
        # Check if column is NOT NULL
        column_info = [col for col in inspector.get_columns(table_name) if col['name'] == column_name]
        if column_info and column_info[0].get('nullable', True) == False:
            op.alter_column(table_name, column_name, nullable=True)
            print(f"Reverted {table_name}.{column_name} to nullable")
    
    # Note: We don't delete the Legacy project or revert data backfill
    # as it's not safe to assume what the original state was

