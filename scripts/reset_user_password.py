#!/usr/bin/env python3
"""Reset password for any existing user. For recovery when access is lost.

Usage:
    python /app/scripts/reset_user_password.py <username> <new_password>

Example (inside api container):
    docker compose exec api python /app/scripts/reset_user_password.py ps_admin NewPass123
"""

import sys
import os

if '/app/src' not in sys.path:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(script_dir, '..', 'src')
    sys.path.insert(0, os.path.abspath(src_dir))

from sqlalchemy import text
from app.db import engine
from app.db_users import get_user_by_username
from app.core.security import get_password_hash


def reset_password(username: str, password: str) -> bool:
    """Reset password for user. Returns True if updated."""
    existing = get_user_by_username(username)
    if not existing:
        print(f"✗ User '{username}' not found")
        return False

    new_hash = get_password_hash(password)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET hashed_password = :pwd, updated_at = now() WHERE username = :user"),
            {"pwd": new_hash, "user": username}
        )
    print(f"✓ Password for '{username}' updated")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python reset_user_password.py <username> <new_password>")
        print("Example: python reset_user_password.py ps_admin NewPass123")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]
    if reset_password(username, password):
        print(f"\nLogin: {username} / {password}")
