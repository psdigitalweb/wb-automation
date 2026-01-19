#!/usr/bin/env python3
"""Database audit script - inventories current DB schema vs code expectations."""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine, inspect, text
from app.settings import SQLALCHEMY_DATABASE_URL

def audit_database():
    """Audit current database schema."""
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    inspector = inspect(engine)
    
    print("=" * 80)
    print("DATABASE AUDIT REPORT")
    print("=" * 80)
    print()
    
    # 1. List all tables
    tables = sorted(inspector.get_table_names())
    print(f"1. TABLES ({len(tables)}):")
    for table in tables:
        print(f"   - {table}")
    print()
    
    # 2. For each table, list columns, indexes, foreign keys
    print("2. TABLE DETAILS:")
    print()
    for table_name in tables:
        print(f"   TABLE: {table_name}")
        
        # Columns
        columns = inspector.get_columns(table_name)
        print(f"      Columns ({len(columns)}):")
        for col in columns:
            nullable = "NULL" if col.get('nullable', True) else "NOT NULL"
            default = f" DEFAULT {col.get('default')}" if col.get('default') else ""
            print(f"        - {col['name']}: {col['type']} {nullable}{default}")
        
        # Primary keys
        pk_constraint = inspector.get_pk_constraint(table_name)
        if pk_constraint and pk_constraint.get('constrained_columns'):
            print(f"      Primary Key: {', '.join(pk_constraint['constrained_columns'])}")
        
        # Foreign keys
        fks = inspector.get_foreign_keys(table_name)
        if fks:
            print(f"      Foreign Keys ({len(fks)}):")
            for fk in fks:
                ref_table = fk['referred_table']
                ref_cols = ', '.join(fk['referred_columns'])
                cols = ', '.join(fk['constrained_columns'])
                print(f"        - {cols} -> {ref_table}({ref_cols})")
        
        # Indexes
        indexes = inspector.get_indexes(table_name)
        if indexes:
            print(f"      Indexes ({len(indexes)}):")
            for idx in indexes:
                unique = "UNIQUE " if idx.get('unique', False) else ""
                cols = ', '.join(idx['column_names'])
                print(f"        - {unique}{idx['name']}: ({cols})")
        
        # Unique constraints
        unique_constraints = inspector.get_unique_constraints(table_name)
        if unique_constraints:
            print(f"      Unique Constraints ({len(unique_constraints)}):")
            for uc in unique_constraints:
                cols = ', '.join(uc['column_names'])
                print(f"        - {uc['name']}: ({cols})")
        
        print()
    
    # 3. Check Alembic version
    print("3. ALEMBIC VERSION:")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar_one_or_none()
            if version:
                print(f"   Current revision: {version}")
            else:
                print("   No Alembic version found (database not initialized)")
    except Exception as e:
        print(f"   Error checking Alembic version: {e}")
    print()
    
    # 4. Expected tables from code
    print("4. EXPECTED TABLES (from code analysis):")
    expected_tables = {
        'users': ['id', 'username', 'email', 'hashed_password', 'is_active', 'is_superuser', 'created_at', 'updated_at'],
        'projects': ['id', 'name', 'description', 'created_by', 'created_at', 'updated_at'],
        'project_members': ['id', 'project_id', 'user_id', 'role', 'created_at', 'updated_at'],
        'marketplaces': ['id', 'code', 'name', 'description', 'is_active', 'created_at', 'updated_at'],
        'project_marketplaces': ['id', 'project_id', 'marketplace_id', 'is_enabled', 'settings_json', 'created_at', 'updated_at'],
        'products': ['id', 'nm_id', 'vendor_code', 'title', 'brand', 'subject_id', 'subject_name', 'description', 'price_u', 'sale_price_u', 'rating', 'feedbacks', 'sizes', 'colors', 'pics', 'dimensions', 'characteristics', 'created_at_api', 'need_kiz', 'raw', 'updated_at', 'first_seen_at', 'project_id'],
        'stock_snapshots': ['id', 'nm_id', 'warehouse_wb_id', 'quantity', 'snapshot_at', 'raw', 'project_id'],
        'price_snapshots': ['id', 'nm_id', 'wb_price', 'wb_discount', 'spp', 'customer_price', 'rrc', 'created_at', 'raw', 'project_id'],
    }
    
    for table_name, expected_cols in expected_tables.items():
        if table_name in tables:
            actual_cols = [c['name'] for c in inspector.get_columns(table_name)]
            missing_cols = set(expected_cols) - set(actual_cols)
            extra_cols = set(actual_cols) - set(expected_cols)
            if missing_cols or extra_cols:
                print(f"   {table_name}:")
                if missing_cols:
                    print(f"      MISSING: {', '.join(sorted(missing_cols))}")
                if extra_cols:
                    print(f"      EXTRA: {', '.join(sorted(extra_cols))}")
        else:
            print(f"   {table_name}: TABLE MISSING")
    print()
    
    print("=" * 80)
    print("AUDIT COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    audit_database()


