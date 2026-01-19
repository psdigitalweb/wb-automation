#!/usr/bin/env python3
"""Fix revision IDs to hex format for specified migrations."""

REVISION_MAPPING = {
    'add_unique_products_project_nm_id': '946d21840243',
    'add_api_token_encrypted': 'e373f63d276a',
    'merge_heads_token_encryption': '670ed0736bfa',
}

DOWN_REVISION_MAPPING = {
    'add_unique_products_project_nm_id': '946d21840243',
    'backfill_project_id_not_null': 'backfill_project_id_not_null',  # Keep as is for now
    'add_project_id_to_data': 'add_project_id_to_data',  # Keep as is for now
}

print("Revision ID mapping:")
for old, new in REVISION_MAPPING.items():
    print(f"  {old} -> {new}")


