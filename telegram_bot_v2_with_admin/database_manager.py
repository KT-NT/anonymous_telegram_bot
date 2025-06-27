#!/usr/bin/env python3
"""
Скрипт для управления базой данных Telegram бота анонимных сообщений
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.models.telegram_user import db, TelegramUser, AnonymousMessage
from src.main import app

def init_database():
    """Инициализация базы данных"""
    with app.app_context():
        print("Создание таблиц базы данных...")
        db.create_all()
        print("✅ База данных успешно инициализирована!")

def clear_database():
    """Очистка базы данных"""
    with app.app_context():
        print("Очистка базы данных...")
        db.drop_all()
        db.create_all()
        print("✅ База данных очищена!")

def show_stats():
    """Показать статистику базы данных"""
    with app.app_context():
        total_users = TelegramUser.query.count()
        total_messages = AnonymousMessage.query.count()
        sent_messages = AnonymousMessage.query.filter_by(is_sent=True).count()
        
        print("\n📊 Статистика базы данных:")
        print(f"👥 Всего пользователей: {total_users}")
        print(f"📩 Всего сообщений: {total_messages}")
        print(f"✅ Отправлено сообщений: {sent_messages}")
        if total_messages > 0:
            delivery_rate = (sent_messages / total_messages) * 100
            print(f"📈 Процент доставки: {delivery_rate:.2f}%")

def list_users():
    """Показать список пользователей"""
    with app.app_context():
        users = TelegramUser.query.all()
        
        print(f"\n👥 Список пользователей ({len(users)}):")
        print("-" * 80)
        for user in users:
            print(f"ID: {user.id}")
            print(f"Telegram ID: {user.telegram_id}")
            print(f"Имя: {user.first_name} {user.last_name or ''}".strip())
            print(f"Username: @{user.username}" if user.username else "Username: не указан")
            print(f"Ссылка ID: {user.unique_link_id}")
            print(f"Создан: {user.created_at}")
            print(f"Сообщений получено: {len(user.messages)}")
            print("-" * 80)

def list_messages():
    """Показать последние сообщения"""
    with app.app_context():
        messages = AnonymousMessage.query.order_by(
            AnonymousMessage.created_at.desc()
        ).limit(10).all()
        
        print(f"\n📩 Последние 10 сообщений:")
        print("-" * 80)
        for msg in messages:
            recipient = TelegramUser.query.get(msg.recipient_id)
            print(f"ID: {msg.id}")
            print(f"Получатель: {recipient.first_name if recipient else 'Неизвестен'}")
            print(f"Текст: {msg.message_text[:100]}{'...' if len(msg.message_text) > 100 else ''}")
            print(f"Отправлено: {'✅' if msg.is_sent else '❌'}")
            print(f"Дата: {msg.created_at}")
            print("-" * 80)

def backup_database():
    """Создать резервную копию базы данных"""
    import shutil
    from datetime import datetime
    
    db_path = os.path.join(os.path.dirname(__file__), 'database', 'app.db')
    backup_name = f"app_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    backup_path = os.path.join(os.path.dirname(__file__), 'database', backup_name)
    
    try:
        shutil.copy2(db_path, backup_path)
        print(f"✅ Резервная копия создана: {backup_name}")
    except Exception as e:
        print(f"❌ Ошибка создания резервной копии: {e}")

def main():
    """Главная функция"""
    if len(sys.argv) < 2:
        print("Использование: python database_manager.py <команда>")
        print("\nДоступные команды:")
        print("  init     - Инициализация базы данных")
        print("  clear    - Очистка базы данных")
        print("  stats    - Показать статистику")
        print("  users    - Показать список пользователей")
        print("  messages - Показать последние сообщения")
        print("  backup   - Создать резервную копию")
        return
    
    command = sys.argv[1].lower()
    
    if command == 'init':
        init_database()
    elif command == 'clear':
        confirm = input("Вы уверены, что хотите очистить базу данных? (yes/no): ")
        if confirm.lower() == 'yes':
            clear_database()
        else:
            print("Операция отменена.")
    elif command == 'stats':
        show_stats()
    elif command == 'users':
        list_users()
    elif command == 'messages':
        list_messages()
    elif command == 'backup':
        backup_database()
    else:
        print(f"Неизвестная команда: {command}")

if __name__ == '__main__':
    main()

