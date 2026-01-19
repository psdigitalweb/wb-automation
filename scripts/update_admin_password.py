#!/usr/bin/env python3
"""Обновить пароль пользователя admin на admin123."""

import sys
import os
sys.path.insert(0, '/app/src')

from sqlalchemy import text
from app.db import engine
from app.core.security import get_password_hash

username = "admin"
password = "admin123"

new_hash = get_password_hash(password)

with engine.begin() as conn:
    conn.execute(
        text("UPDATE users SET hashed_password = :pwd, updated_at = now() WHERE username = :user"),
        {"pwd": new_hash, "user": username}
    )

print(f"✓ Пароль для пользователя '{username}' обновлен на '{password}'")
