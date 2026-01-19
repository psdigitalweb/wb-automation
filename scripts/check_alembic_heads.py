#!/usr/bin/env python3
"""Check Alembic heads by analyzing migration files."""

import re
import os
from pathlib import Path

versions_dir = Path(__file__).parent.parent / "alembic" / "versions"

revisions = {}
down_revisions = set()

# Parse all migration files
for file in versions_dir.glob("*.py"):
    content = file.read_text(encoding='utf-8')
    
    # Extract revision
    rev_match = re.search(r"revision:\s*str\s*=\s*['\"]([^'\"]+)['\"]", content)
    if not rev_match:
        continue
    
    revision = rev_match.group(1)
    
    # Extract down_revision (can be string, None, or tuple)
    down_match = re.search(r"down_revision.*?=\s*(\([^)]+\)|['\"]([^'\"]+)['\"]|None)", content)
    if down_match:
        down_str = down_match.group(0)
        if down_str.strip().endswith('None'):
            down_revision = None
        elif '(' in down_str:
            # Tuple format: ('rev1', 'rev2')
            tuple_match = re.search(r"\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]+)['\"]\)", down_str)
            if tuple_match:
                down_revision = (tuple_match.group(1), tuple_match.group(2))
            else:
                down_revision = None
        else:
            down_revision = down_match.group(2) if down_match.group(2) else None
    else:
        down_revision = None
    
    revisions[revision] = {
        'file': file.name,
        'down': down_revision
    }
    
    if down_revision:
        down_revisions.add(down_revision)

# Find heads (revisions that are not down_revision for any other migration)
# But also check for merge migrations (down_revision is a tuple)
heads = []
for rev, info in revisions.items():
    # Check if this revision is a down_revision for any other migration
    is_down_revision = False
    for other_rev, other_info in revisions.items():
        if other_rev == rev:
            continue
        other_down = other_info['down']
        if isinstance(other_down, tuple):
            # Merge migration - check if rev is in the tuple
            if rev in other_down:
                is_down_revision = True
                break
        elif other_down == rev:
            is_down_revision = True
            break
    
    if not is_down_revision:
        heads.append(rev)

print("=" * 80)
print("ALEMBIC HEADS ANALYSIS")
print("=" * 80)
print()
print(f"Total migrations: {len(revisions)}")
print(f"Heads found: {len(heads)}")
print()
print("HEADS:")
for head in sorted(heads):
    info = revisions[head]
    print(f"  - {head}")
    print(f"    File: {info['file']}")
    print(f"    Down revision: {info['down']}")
    print()

if len(heads) > 1:
    print("=" * 80)
    print("MERGE REQUIRED")
    print("=" * 80)
    print(f"Need to merge: {', '.join(sorted(heads))}")
else:
    print("=" * 80)
    print("NO MERGE NEEDED - Single head")
    print("=" * 80)

