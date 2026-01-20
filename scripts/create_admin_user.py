#!/usr/bin/env python3
"""Script to create/update admin user with specified password.

Usage:
    python /app/scripts/create_admin_user.py [password]
    
If password is not provided, defaults to "admin123".
Script is idempotent: creates user if missing, updates password if different.
"""

import sys
import os

# Ensure we can import app modules
# In container: PYTHONPATH=/app/src, script is at /app/scripts/create_admin_user.py
# On host: script is at scripts/create_admin_user.py, need to add ../src
if '/app/src' not in sys.path:
    # Running from host, add src to path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(script_dir, '..', 'src')
    sys.path.insert(0, os.path.abspath(src_dir))

from sqlalchemy import text
from app.db import engine
from app.db_users import get_user_by_username, create_user
from app.core.security import get_password_hash, verify_password

def create_or_update_admin(password: str = "admin123") -> None:
    """Создать или обновить пользователя admin с указанным паролем."""
    username = "admin"
    
    # Проверяем, существует ли пользователь
    existing_user = get_user_by_username(username)
    
    if existing_user:
        # Пользователь существует, проверяем пароль
        current_hash = existing_user["hashed_password"]
        
        if verify_password(password, current_hash):
            print(f"✓ Пользователь '{username}' уже существует с этим паролем")
            return
        
        # Пароль не совпадает - обновляем
        print(f"Пользователь '{username}' существует, обновляем пароль и устанавливаем is_superuser=true...")
        new_hash = get_password_hash(password)
        
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE users 
                    SET hashed_password = :password, is_superuser = true, updated_at = now()
                    WHERE username = :username
                """),
                {"username": username, "password": new_hash}
            )
        
        print(f"✓ Пароль для пользователя '{username}' обновлен, is_superuser=true установлен")
    else:
        # Пользователь не существует - создаем
        print(f"Создаем пользователя '{username}'...")
        new_hash = get_password_hash(password)
        admin_user = create_user(
            username=username,
            email="admin@example.com",
            hashed_password=new_hash,
            is_superuser=True
        )
        print(f"✓ Пользователь '{username}' создан (id={admin_user['id']})")
    
    print(f"\nУчетные данные:")
    print(f"  Username: {username}")
    print(f"  Password: {password}")

if __name__ == "__main__":
    # Можно передать пароль как аргумент командной строки
    password = sys.argv[1] if len(sys.argv) > 1 else "admin123"
    create_or_update_admin(password)
