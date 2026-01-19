#!/usr/bin/env python3
"""
Diagnose Alembic and database schema state.

This script:
1. Checks Alembic current version vs heads
2. Lists tables and key columns
3. Checks for critical fields (project_id, api_token_encrypted)
4. Provides recommendation: upgrade, repair+stamp, or reset
"""

import os
import sys
import subprocess
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from sqlalchemy import create_engine, inspect, text
    from app.db import engine
except ImportError as e:
    print(f"ERROR: Cannot import app modules: {e}")
    print("Make sure you're running this from the project root or in docker container")
    sys.exit(1)


def get_alembic_current():
    """Get current Alembic version from database."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            row = result.fetchone()
            if row:
                return row[0]
            return None
    except Exception as e:
        print(f"WARNING: Could not read alembic_version: {e}")
        return None


def get_alembic_heads():
    """Get Alembic heads via alembic command."""
    try:
        result = subprocess.run(
            ["alembic", "heads", "--verbose"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            # Extract revision IDs from output - heads are usually the first non-empty lines
            heads = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Try to extract revision ID (hex string or migration name)
                # Format is usually: "revision_id (head)" or just "revision_id"
                parts = line.split()
                for part in parts:
                    part = part.strip('()')
                    # Revision IDs: hex (12 chars) or names (add_*, merge_*, etc.)
                    if (len(part) >= 8 and (all(c in '0123456789abcdef' for c in part.lower()) or 
                        part.startswith('add_') or part.startswith('merge_') or part.startswith('71fcc51a5119'))):
                        if part not in heads:
                            heads.append(part)
                        break
            return heads if heads else None
        return None
    except Exception as e:
        print(f"WARNING: Could not get alembic heads: {e}")
        return None


def get_tables(inspector):
    """Get list of tables in public schema."""
    try:
        return inspector.get_table_names(schema='public')
    except Exception as e:
        print(f"ERROR: Could not get tables: {e}")
        return []


def get_columns(inspector, table_name):
    """Get column names for a table."""
    try:
        columns = inspector.get_columns(table_name)
        return [col['name'] for col in columns]
    except Exception as e:
        return None


def get_constraints(inspector, table_name):
    """Get unique constraints for a table."""
    try:
        constraints = inspector.get_unique_constraints(table_name)
        return constraints
    except Exception as e:
        return []


def check_indexes(inspector, table_name):
    """Get indexes for a table."""
    try:
        indexes = inspector.get_indexes(table_name)
        return [idx['name'] for idx in indexes]
    except Exception as e:
        return []


def diagnose():
    """Main diagnosis function."""
    print("=" * 80)
    print("ALEMBIC & DATABASE SCHEMA DIAGNOSIS")
    print("=" * 80)
    print()
    
    # 1. Check Alembic state
    print("1. ALEMBIC STATE")
    print("-" * 80)
    current = get_alembic_current()
    heads = get_alembic_heads()
    
    print(f"Current version: {current if current else '(no alembic_version table)'}")
    print(f"Heads: {', '.join(heads) if heads else '(unknown)'}")
    
    if current and heads:
        if current in heads:
            print("✅ Current == Head (schema should be in sync)")
        else:
            print("⚠️  Current != Head (schema drift detected)")
    elif not current:
        print("⚠️  No current version (database may be uninitialized)")
    print()
    
    # 2. Check database schema
    print("2. DATABASE SCHEMA")
    print("-" * 80)
    inspector = inspect(engine)
    tables = get_tables(inspector)
    
    print(f"Tables in public schema: {len(tables)}")
    print(f"Tables: {', '.join(sorted(tables))}")
    print()
    
    # 3. Check key tables and columns
    print("3. KEY TABLES AND COLUMNS")
    print("-" * 80)
    
    key_tables = ['users', 'projects', 'project_members', 'marketplaces', 
                  'project_marketplaces', 'products', 'stock_snapshots', 'price_snapshots']
    
    table_status = {}
    for table in key_tables:
        if table in tables:
            columns = get_columns(inspector, table)
            table_status[table] = {
                'exists': True,
                'columns': columns if columns else []
            }
            print(f"✅ {table}: {len(columns) if columns else 0} columns")
            if columns:
                key_cols = [c for c in columns if c in ['id', 'project_id', 'api_token_encrypted', 'nm_id', 'title']]
                if key_cols:
                    print(f"   Key columns: {', '.join(key_cols)}")
        else:
            table_status[table] = {'exists': False, 'columns': []}
            print(f"❌ {table}: MISSING")
    print()
    
    # 4. Check critical fields
    print("4. CRITICAL FIELDS CHECK")
    print("-" * 80)
    
    issues = []
    
    # Check project_id in data tables
    data_tables = ['products', 'stock_snapshots', 'price_snapshots']
    for table in data_tables:
        if table_status.get(table, {}).get('exists'):
            cols = table_status[table].get('columns', [])
            if 'project_id' not in cols:
                issues.append(f"❌ {table}.project_id MISSING")
            else:
                print(f"✅ {table}.project_id exists")
        else:
            if table in tables:  # Table exists but wasn't in key_tables check
                print(f"⚠️  {table}: exists but not checked")
    
    # Check api_token_encrypted in project_marketplaces
    if table_status.get('project_marketplaces', {}).get('exists'):
        cols = table_status['project_marketplaces'].get('columns', [])
        if 'api_token_encrypted' not in cols:
            issues.append("❌ project_marketplaces.api_token_encrypted MISSING")
        else:
            print("✅ project_marketplaces.api_token_encrypted exists")
    
    # Check UNIQUE constraint on (project_id, nm_id) for products
    if table_status.get('products', {}).get('exists'):
        constraints = get_constraints(inspector, 'products')
        has_project_nm_unique = False
        for uc in constraints:
            if set(uc['column_names']) == {'project_id', 'nm_id'}:
                has_project_nm_unique = True
                break
        if not has_project_nm_unique:
            issues.append("❌ products: UNIQUE(project_id, nm_id) MISSING")
        else:
            print("✅ products: UNIQUE(project_id, nm_id) exists")
    
    if issues:
        print()
        print("ISSUES FOUND:")
        for issue in issues:
            print(f"  {issue}")
    print()
    
    # 5. Determine correct stamp revision based on schema
    print("5. DETERMINING STAMP REVISION")
    print("-" * 80)
    
    stamp_revision = None
    if 'project_marketplaces' in tables:
        cols = table_status.get('project_marketplaces', {}).get('columns', [])
        if 'api_token_encrypted' in cols:
            stamp_revision = '71fcc51a5119'  # repair migration (head)
        else:
            stamp_revision = '670ed0736bfa'  # merge head (before repair)
    elif 'marketplaces' in tables:
        stamp_revision = 'add_marketplaces_tables'
    elif 'projects' in tables or 'project_members' in tables:
        stamp_revision = 'add_projects_tables'
    elif 'users' in tables:
        stamp_revision = 'add_users_table'
    
    if stamp_revision:
        print(f"Detected schema state suggests stamp to: {stamp_revision}")
    else:
        print("Unable to determine stamp revision from schema")
    print()
    
    # 6. Recommendation
    print("6. RECOMMENDATION")
    print("-" * 80)
    
    if not current and not tables:
        print("✅ RECOMMENDATION: Fresh database")
        print("   Command: alembic upgrade head")
        return "fresh"
    elif not current and tables:
        print("⚠️  RECOMMENDATION: Database has tables but no alembic_version")
        if stamp_revision:
            print(f"   Detected revision: {stamp_revision}")
            print(f"   Command: alembic stamp {stamp_revision} && alembic upgrade head")
        else:
            print("   Option 1 (SAFE): Reset volume and run 'alembic upgrade head'")
            print("   Option 2 (RISKY): Manual stamp required - review schema manually")
        return "no_version"
    elif current and heads and current in heads:
        if issues:
            print("⚠️  RECOMMENDATION: Current == Head but schema has issues")
            print("   Run repair migration: 'alembic upgrade head' (will apply repair migration)")
            return "repair_needed"
        else:
            print("✅ RECOMMENDATION: Database is in sync - no action needed")
            return "ok"
    elif current and heads and current not in heads:
        print("⚠️  RECOMMENDATION: Schema drift - current != head")
        if issues:
            print("   Option 1 (SAFE): Reset volume and run 'alembic upgrade head'")
            print("   Option 2: Apply repair migration + stamp to head then upgrade")
        else:
            print("   Schema looks complete - stamp to head and verify")
            if len(heads) == 1:
                print(f"   Command: alembic stamp {heads[0]} && alembic upgrade head")
        return "drift"
    else:
        print("⚠️  RECOMMENDATION: Unable to determine state - manual review needed")
        return "unknown"
    
    print()


if __name__ == "__main__":
    try:
        diagnose()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

