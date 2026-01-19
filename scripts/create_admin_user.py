#!/usr/bin/env python3
"""Скрипт для создания/обновления пользователя admin с паролем admin123."""

import sys
import os

# Добавляем путь к src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

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
        print(f"Пользователь '{username}' существует, обновляем пароль...")
        new_hash = get_password_hash(password)
        
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE users 
                    SET hashed_password = :password, updated_at = now()
                    WHERE username = :username
                """),
                {"username": username, "password": new_hash}
            )
        
        print(f"✓ Пароль для пользователя '{username}' обновлен")
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
