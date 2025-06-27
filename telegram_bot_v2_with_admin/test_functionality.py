#!/usr/bin/env python3
"""
Тестовый скрипт для проверки функциональности бота без реального Telegram API
"""

import os
import sys
import requests
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.models.telegram_user import db, TelegramUser, AnonymousMessage
from src.main import app

def test_database_operations():
    """Тестирование операций с базой данных"""
    print("🧪 Тестирование операций с базой данных...")
    
    with app.app_context():
        # Создаем тестового пользователя
        test_user = TelegramUser(
            telegram_id=123456789,
            username="testuser",
            first_name="Тест",
            last_name="Пользователь"
        )
        db.session.add(test_user)
        db.session.commit()
        
        print(f"✅ Создан тестовый пользователь: {test_user.first_name}")
        print(f"   Уникальная ссылка: {test_user.unique_link_id}")
        
        # Создаем тестовое сообщение
        test_message = AnonymousMessage(
            recipient_id=test_user.id,
            message_text="Это тестовое анонимное сообщение!",
            sender_ip="127.0.0.1"
        )
        db.session.add(test_message)
        db.session.commit()
        
        print(f"✅ Создано тестовое сообщение: {test_message.id}")
        
        return test_user

def test_api_endpoints():
    """Тестирование API endpoints"""
    print("\n🧪 Тестирование API endpoints...")
    
    base_url = "http://localhost:5000"
    
    # Тестируем статистику
    try:
        response = requests.get(f"{base_url}/api/stats")
        if response.status_code == 200:
            stats = response.json()
            print(f"✅ API статистики работает: {stats}")
        else:
            print(f"❌ Ошибка API статистики: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка подключения к API статистики: {e}")

def test_web_form(test_user):
    """Тестирование веб-формы отправки сообщений"""
    print("\n🧪 Тестирование веб-формы...")
    
    base_url = "http://localhost:5000"
    
    # Тестируем страницу отправки сообщения
    try:
        response = requests.get(f"{base_url}/send/{test_user.unique_link_id}")
        if response.status_code == 200:
            print("✅ Страница отправки сообщения загружается")
        else:
            print(f"❌ Ошибка загрузки страницы: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка подключения к веб-форме: {e}")
    
    # Тестируем отправку сообщения через POST
    try:
        test_message_data = {
            'message': 'Тестовое анонимное сообщение через веб-форму!'
        }
        response = requests.post(
            f"{base_url}/send/{test_user.unique_link_id}",
            data=test_message_data
        )
        if response.status_code == 200:
            print("✅ Отправка сообщения через веб-форму работает")
        else:
            print(f"❌ Ошибка отправки сообщения: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка отправки через веб-форму: {e}")

def test_invalid_link():
    """Тестирование обработки недействительных ссылок"""
    print("\n🧪 Тестирование недействительных ссылок...")
    
    base_url = "http://localhost:5000"
    
    try:
        response = requests.get(f"{base_url}/send/invalid_link_id_12345")
        if response.status_code == 404:
            print("✅ Недействительные ссылки корректно обрабатываются (404)")
        else:
            print(f"❌ Неожиданный код ответа для недействительной ссылки: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка тестирования недействительной ссылки: {e}")

def cleanup_test_data():
    """Очистка тестовых данных"""
    print("\n🧹 Очистка тестовых данных...")
    
    with app.app_context():
        # Удаляем тестовые сообщения
        AnonymousMessage.query.filter_by(sender_ip="127.0.0.1").delete()
        
        # Удаляем тестового пользователя
        TelegramUser.query.filter_by(telegram_id=123456789).delete()
        
        db.session.commit()
        print("✅ Тестовые данные очищены")

def main():
    """Главная функция тестирования"""
    print("🚀 Запуск тестов функциональности бота...")
    print("=" * 50)
    
    # Проверяем, что Flask-сервер запущен
    try:
        response = requests.get("http://localhost:5000")
        if response.status_code != 200:
            print("❌ Flask-сервер не запущен или недоступен")
            print("   Запустите сервер командой: python src/main.py")
            return
    except Exception as e:
        print("❌ Не удается подключиться к Flask-серверу")
        print("   Запустите сервер командой: python src/main.py")
        return
    
    print("✅ Flask-сервер доступен")
    
    # Запускаем тесты
    test_user = test_database_operations()
    test_api_endpoints()
    test_web_form(test_user)
    test_invalid_link()
    
    print("\n" + "=" * 50)
    print("🎉 Тестирование завершено!")
    
    # Спрашиваем, нужно ли очистить тестовые данные
    cleanup = input("\nОчистить тестовые данные? (y/n): ").lower()
    if cleanup == 'y':
        cleanup_test_data()

if __name__ == '__main__':
    main()

