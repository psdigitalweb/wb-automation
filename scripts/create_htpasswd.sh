#!/bin/bash
# Скрипт для создания .htpasswd файла для Adminer

HTPASSWD_FILE="nginx/.htpasswd"

if [ ! -f "$HTPASSWD_FILE" ]; then
    echo "Создание файла .htpasswd для Adminer..."
    
    # Проверяем, установлен ли htpasswd
    if ! command -v htpasswd &> /dev/null; then
        echo "ОШИБКА: htpasswd не установлен!"
        echo ""
        echo "Установите apache2-utils:"
        echo "  Linux/Debian: sudo apt-get install apache2-utils"
        echo "  Linux/RedHat: sudo yum install httpd-tools"
        echo "  Mac: brew install httpd"
        echo "  Windows: используйте WSL или Git Bash"
        exit 1
    fi
    
    # Создаем файл с пользователем admin
    htpasswd -c "$HTPASSWD_FILE" admin
    echo ""
    echo "Файл $HTPASSWD_FILE создан!"
    echo "Пользователь: admin"
    echo "Пароль: (введите при запросе)"
else
    echo "Файл $HTPASSWD_FILE уже существует."
    echo "Для добавления нового пользователя используйте:"
    echo "  htpasswd $HTPASSWD_FILE username"
fi






