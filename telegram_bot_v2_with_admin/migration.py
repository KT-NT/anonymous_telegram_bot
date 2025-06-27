#!/usr/bin/env python3
"""
Скрипт миграции базы данных для добавления админ-панели и VIP-функций
"""

import os
import sys
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.models.telegram_user import db as old_db, TelegramUser as OldTelegramUser, AnonymousMessage as OldAnonymousMessage
from src.models.telegram_user_v2 import db as new_db, TelegramUser, AnonymousMessage, AdminSession, AdminAction, VIPMessageSettings
from src.main import app

def backup_database():
    """Создает резервную копию текущей базы данных"""
    db_path = os.path.join(os.path.dirname(__file__), 'src', 'database', 'app.db')
    backup_name = f"app_backup_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    backup_path = os.path.join(os.path.dirname(__file__), 'src', 'database', backup_name)
    
    try:
        if os.path.exists(db_path):
            shutil.copy2(db_path, backup_path)
            print(f"✅ Резервная копия создана: {backup_name}")
            return backup_path
        else:
            print("⚠️ Файл базы данных не найден, резервная копия не создана")
            return None
    except Exception as e:
        print(f"❌ Ошибка создания резервной копии: {e}")
        return None

def migrate_data():
    """Выполняет миграцию данных из старой схемы в новую"""
    print("🔄 Начинаем миграцию данных...")
    
    with app.app_context():
        # Получаем все данные из старых таблиц
        old_users = old_db.session.query(OldTelegramUser).all()
        old_messages = old_db.session.query(OldAnonymousMessage).all()
        
        print(f"📊 Найдено пользователей: {len(old_users)}")
        print(f"📊 Найдено сообщений: {len(old_messages)}")
        
        # Создаем новые таблицы
        new_db.create_all()
        
        # Мигрируем пользователей
        user_mapping = {}  # Старый ID -> Новый ID
        
        for old_user in old_users:
            new_user = TelegramUser(
                telegram_id=old_user.telegram_id,
                username=old_user.username,
                first_name=old_user.first_name,
                last_name=old_user.last_name
            )
            new_user.unique_link_id = old_user.unique_link_id
            new_user.created_at = old_user.created_at
            
            new_db.session.add(new_user)
            new_db.session.flush()  # Получаем ID
            
            user_mapping[old_user.id] = new_user.id
            
        print("✅ Пользователи мигрированы")
        
        # Мигрируем сообщения
        for old_message in old_messages:
            new_message = AnonymousMessage(
                recipient_id=user_mapping[old_message.recipient_id],
                message_text=old_message.message_text,
                sender_ip=old_message.sender_ip,
                created_at=old_message.created_at,
                is_sent=old_message.is_sent
            )
            
            new_db.session.add(new_message)
            
        print("✅ Сообщения мигрированы")
        
        # Сохраняем изменения
        new_db.session.commit()
        print("✅ Миграция завершена успешно!")

def setup_admin_users():
    """Настраивает администраторов системы"""
    print("\n👑 Настройка администраторов...")
    
    # Список Telegram ID администраторов (замените на реальные)
    admin_telegram_ids = [
        # 123456789,  # Замените на реальный Telegram ID
        # 987654321,  # Добавьте дополнительных администраторов
    ]
    
    if not admin_telegram_ids:
        print("⚠️ Список администраторов пуст. Добавьте Telegram ID в скрипт миграции.")
        print("   Редактируйте файл migration.py и добавьте ID в список admin_telegram_ids")
        return
    
    with app.app_context():
        for telegram_id in admin_telegram_ids:
            user = TelegramUser.query.filter_by(telegram_id=telegram_id).first()
            if user:
                user.is_admin = True
                print(f"✅ Пользователь {user.get_display_name()} назначен администратором")
            else:
                print(f"⚠️ Пользователь с Telegram ID {telegram_id} не найден")
        
        new_db.session.commit()

def verify_migration():
    """Проверяет результаты миграции"""
    print("\n🔍 Проверка результатов миграции...")
    
    with app.app_context():
        users_count = TelegramUser.query.count()
        messages_count = AnonymousMessage.query.count()
        admins_count = TelegramUser.query.filter_by(is_admin=True).count()
        vips_count = TelegramUser.query.filter_by(is_vip=True).count()
        
        print(f"📊 Пользователей в новой БД: {users_count}")
        print(f"📊 Сообщений в новой БД: {messages_count}")
        print(f"👑 Администраторов: {admins_count}")
        print(f"⭐ VIP-пользователей: {vips_count}")
        
        # Проверяем структуру таблиц
        inspector = new_db.inspect(new_db.engine)
        tables = inspector.get_table_names()
        
        expected_tables = ['telegram_user', 'anonymous_message', 'admin_session', 'admin_action', 'vip_message_settings']
        
        print(f"\n📋 Таблицы в базе данных: {tables}")
        
        for table in expected_tables:
            if table in tables:
                print(f"✅ Таблица {table} создана")
            else:
                print(f"❌ Таблица {table} не найдена")

def main():
    """Главная функция миграции"""
    print("🚀 Запуск миграции базы данных для админ-панели и VIP-функций")
    print("=" * 70)
    
    # Создаем резервную копию
    backup_path = backup_database()
    
    if backup_path:
        print(f"💾 Резервная копия сохранена в: {backup_path}")
    
    # Подтверждение миграции
    confirm = input("\nПродолжить миграцию? (yes/no): ").lower()
    if confirm != 'yes':
        print("❌ Миграция отменена")
        return
    
    try:
        # Выполняем миграцию
        migrate_data()
        
        # Настраиваем администраторов
        setup_admin_users()
        
        # Проверяем результаты
        verify_migration()
        
        print("\n" + "=" * 70)
        print("🎉 Миграция завершена успешно!")
        print("\n📝 Следующие шаги:")
        print("1. Обновите src/models/telegram_user.py новой версией")
        print("2. Добавьте Telegram ID администраторов в список admin_telegram_ids")
        print("3. Перезапустите приложение")
        print("4. Протестируйте админ-панель")
        
    except Exception as e:
        print(f"\n❌ Ошибка миграции: {e}")
        print("💡 Восстановите базу данных из резервной копии если необходимо")
        
        if backup_path:
            print(f"   cp {backup_path} src/database/app.db")

if __name__ == '__main__':
    main()

