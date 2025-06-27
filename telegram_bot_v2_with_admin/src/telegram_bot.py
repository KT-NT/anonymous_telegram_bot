import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
import sys

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(__file__))

# Импортируем обновленные модели
try:
    from models.telegram_user_v2 import db, TelegramUser, AnonymousMessage, AdminSession, AdminAction, VIPMessageSettings
    MODELS_V2_AVAILABLE = True
except ImportError:
    from models.telegram_user import db, TelegramUser, AnonymousMessage
    MODELS_V2_AVAILABLE = False

from main_v2 import create_app

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота (получите у @BotFather)
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    logger.warning("TELEGRAM_BOT_TOKEN не установлен. Бот будет недоступен.")
    BOT_TOKEN = "dummy_token"

# URL веб-приложения
WEB_APP_URL = os.environ.get('WEB_APP_URL', 'http://localhost:5000')

# Создаем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Flask приложение для работы с базой данных
flask_app = create_app()

def get_user_or_create(telegram_user: types.User):
    """Получает пользователя из БД или создает нового"""
    with flask_app.app_context():
        user = TelegramUser.query.filter_by(telegram_id=telegram_user.id).first()
        
        if not user:
            user = TelegramUser(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name
            )
            db.session.add(user)
            db.session.commit()
            logger.info(f"Создан новый пользователь: {user.telegram_id}")
        
        return user

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user = get_user_or_create(message.from_user)
    
    # Формируем ссылку для анонимных сообщений
    anonymous_link = user.get_anonymous_link(WEB_APP_URL)
    
    # Проверяем VIP-статус
    vip_status = ""
    if MODELS_V2_AVAILABLE:
        try:
            if user.is_vip:
                vip_status = "\n\n⭐ У вас VIP-статус! Вы можете получать неанонимные сообщения с именем отправителя."
        except AttributeError:
            pass
    
    welcome_text = f"""
🤖 Добро пожаловать в бота анонимных сообщений!

👤 Ваше имя: {user.get_display_name()}
🔗 Ваша ссылка для получения анонимных сообщений:
{anonymous_link}

📝 Поделитесь этой ссылкой с друзьями, и они смогут отправлять вам анонимные сообщения!

💡 Команды:
/start - Показать эту информацию
/link - Получить вашу ссылку
/stats - Статистика ваших сообщений{vip_status}

🔒 Все сообщения полностью анонимны и безопасны.
"""
    
    await message.answer(welcome_text)

@dp.message(Command("link"))
async def cmd_link(message: Message):
    """Обработчик команды /link"""
    user = get_user_or_create(message.from_user)
    anonymous_link = user.get_anonymous_link(WEB_APP_URL)
    
    await message.answer(f"🔗 Ваша ссылка для анонимных сообщений:\n{anonymous_link}")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    """Обработчик команды /stats"""
    user = get_user_or_create(message.from_user)
    
    with flask_app.app_context():
        total_messages = AnonymousMessage.query.filter_by(recipient_id=user.id).count()
        sent_messages = AnonymousMessage.query.filter_by(recipient_id=user.id, is_sent=True).count()
        
        stats_text = f"""
📊 Ваша статистика:

📩 Всего сообщений: {total_messages}
✅ Доставлено: {sent_messages}
"""
        
        if MODELS_V2_AVAILABLE:
            try:
                anonymous_messages = AnonymousMessage.query.filter_by(
                    recipient_id=user.id, 
                    is_anonymous=True
                ).count()
                non_anonymous_messages = AnonymousMessage.query.filter_by(
                    recipient_id=user.id, 
                    is_anonymous=False
                ).count()
                
                stats_text += f"🕶️ Анонимных: {anonymous_messages}\n"
                stats_text += f"👤 Неанонимных: {non_anonymous_messages}\n"
                
                if user.is_vip:
                    stats_text += f"\n⭐ VIP-статус: Активен"
                    if user.vip_granted_at:
                        stats_text += f"\n📅 VIP с: {user.vip_granted_at.strftime('%d.%m.%Y')}"
                
            except AttributeError:
                pass
        
        await message.answer(stats_text)

# Админ-команды (только для V2)
if MODELS_V2_AVAILABLE:
    @dp.message(Command("admin"))
    async def cmd_admin(message: Message):
        """Обработчик команды /admin"""
        user = get_user_or_create(message.from_user)
        
        with flask_app.app_context():
            if not user.is_admin:
                await message.answer("❌ У вас нет прав администратора.")
                return
            
            # Создаем сессию администратора
            try:
                admin_session = AdminSession(admin_id=user.id)
                db.session.add(admin_session)
                db.session.commit()
                
                admin_link = f"{WEB_APP_URL}/admin/dashboard"
                
                await message.answer(f"""
👑 Добро пожаловать в админ-панель!

🔗 Ссылка: {admin_link}
🔑 Токен сессии: `{admin_session.session_token}`

⚠️ Токен действителен 24 часа. Не передавайте его третьим лицам.

💡 Команды администратора:
/admin - Получить доступ к админ-панели
/grant_vip [user_id] - Выдать VIP-статус
/revoke_vip [user_id] - Отозвать VIP-статус
/user_info [user_id] - Информация о пользователе
""", parse_mode="Markdown")
                
            except Exception as e:
                logger.error(f"Ошибка создания админ-сессии: {e}")
                await message.answer("❌ Ошибка создания сессии администратора.")

    @dp.message(Command("grant_vip"))
    async def cmd_grant_vip(message: Message):
        """Обработчик команды /grant_vip"""
        admin_user = get_user_or_create(message.from_user)
        
        with flask_app.app_context():
            if not admin_user.is_admin:
                await message.answer("❌ У вас нет прав администратора.")
                return
            
            # Извлекаем user_id из команды
            try:
                parts = message.text.split()
                if len(parts) < 2:
                    await message.answer("❌ Использование: /grant_vip [user_id]")
                    return
                
                target_user_id = int(parts[1])
                target_user = TelegramUser.query.filter_by(telegram_id=target_user_id).first()
                
                if not target_user:
                    await message.answer(f"❌ Пользователь с ID {target_user_id} не найден.")
                    return
                
                if target_user.is_vip:
                    await message.answer(f"⚠️ Пользователь {target_user.get_display_name()} уже имеет VIP-статус.")
                    return
                
                # Выдаем VIP-статус
                target_user.grant_vip(admin_user)
                db.session.commit()
                
                await message.answer(f"✅ VIP-статус выдан пользователю {target_user.get_display_name()}")
                
                # Уведомляем пользователя
                try:
                    await bot.send_message(
                        target_user.telegram_id,
                        "🎉 Поздравляем! Вам выдан VIP-статус!\n\n"
                        "⭐ Теперь вы можете получать неанонимные сообщения с именем отправителя.\n"
                        "Используйте команду /stats для просмотра обновленной информации."
                    )
                except Exception as e:
                    logger.warning(f"Не удалось уведомить пользователя {target_user.telegram_id}: {e}")
                
            except ValueError:
                await message.answer("❌ Неверный формат user_id. Используйте числовой ID.")
            except Exception as e:
                logger.error(f"Ошибка выдачи VIP: {e}")
                await message.answer("❌ Ошибка при выдаче VIP-статуса.")

    @dp.message(Command("revoke_vip"))
    async def cmd_revoke_vip(message: Message):
        """Обработчик команды /revoke_vip"""
        admin_user = get_user_or_create(message.from_user)
        
        with flask_app.app_context():
            if not admin_user.is_admin:
                await message.answer("❌ У вас нет прав администратора.")
                return
            
            # Извлекаем user_id из команды
            try:
                parts = message.text.split()
                if len(parts) < 2:
                    await message.answer("❌ Использование: /revoke_vip [user_id]")
                    return
                
                target_user_id = int(parts[1])
                target_user = TelegramUser.query.filter_by(telegram_id=target_user_id).first()
                
                if not target_user:
                    await message.answer(f"❌ Пользователь с ID {target_user_id} не найден.")
                    return
                
                if not target_user.is_vip:
                    await message.answer(f"⚠️ Пользователь {target_user.get_display_name()} не имеет VIP-статуса.")
                    return
                
                # Отзываем VIP-статус
                target_user.revoke_vip(admin_user)
                db.session.commit()
                
                await message.answer(f"✅ VIP-статус отозван у пользователя {target_user.get_display_name()}")
                
                # Уведомляем пользователя
                try:
                    await bot.send_message(
                        target_user.telegram_id,
                        "📢 Ваш VIP-статус был отозван.\n\n"
                        "Теперь вы будете получать только анонимные сообщения."
                    )
                except Exception as e:
                    logger.warning(f"Не удалось уведомить пользователя {target_user.telegram_id}: {e}")
                
            except ValueError:
                await message.answer("❌ Неверный формат user_id. Используйте числовой ID.")
            except Exception as e:
                logger.error(f"Ошибка отзыва VIP: {e}")
                await message.answer("❌ Ошибка при отзыве VIP-статуса.")

    @dp.message(Command("user_info"))
    async def cmd_user_info(message: Message):
        """Обработчик команды /user_info"""
        admin_user = get_user_or_create(message.from_user)
        
        with flask_app.app_context():
            if not admin_user.is_admin:
                await message.answer("❌ У вас нет прав администратора.")
                return
            
            # Извлекаем user_id из команды
            try:
                parts = message.text.split()
                if len(parts) < 2:
                    await message.answer("❌ Использование: /user_info [user_id]")
                    return
                
                target_user_id = int(parts[1])
                target_user = TelegramUser.query.filter_by(telegram_id=target_user_id).first()
                
                if not target_user:
                    await message.answer(f"❌ Пользователь с ID {target_user_id} не найден.")
                    return
                
                # Собираем информацию о пользователе
                total_messages = AnonymousMessage.query.filter_by(recipient_id=target_user.id).count()
                
                info_text = f"""
👤 Информация о пользователе:

🆔 Telegram ID: {target_user.telegram_id}
📝 Имя: {target_user.get_display_name()}
👤 Username: @{target_user.username or 'не указан'}
📅 Регистрация: {target_user.created_at.strftime('%d.%m.%Y %H:%M') if target_user.created_at else 'неизвестно'}
📩 Сообщений получено: {total_messages}

⭐ VIP-статус: {'Да' if target_user.is_vip else 'Нет'}
"""
                
                if target_user.is_vip and target_user.vip_granted_at:
                    info_text += f"📅 VIP с: {target_user.vip_granted_at.strftime('%d.%m.%Y %H:%M')}\n"
                
                if target_user.is_admin:
                    info_text += "👑 Администратор: Да\n"
                
                info_text += f"\n🔗 Ссылка: {target_user.get_anonymous_link(WEB_APP_URL)}"
                
                await message.answer(info_text)
                
            except ValueError:
                await message.answer("❌ Неверный формат user_id. Используйте числовой ID.")
            except Exception as e:
                logger.error(f"Ошибка получения информации о пользователе: {e}")
                await message.answer("❌ Ошибка при получении информации о пользователе.")

@dp.message()
async def handle_message(message: Message):
    """Обработчик всех остальных сообщений"""
    await message.answer(
        "🤖 Я бот для анонимных сообщений!\n\n"
        "💡 Доступные команды:\n"
        "/start - Начать работу\n"
        "/link - Получить вашу ссылку\n"
        "/stats - Статистика сообщений\n\n"
        "❓ Если у вас есть вопросы, используйте команду /start для получения подробной информации."
    )

async def send_message_to_user(user_id: int, message_text: str):
    """Отправляет сообщение пользователю в Telegram"""
    try:
        await bot.send_message(user_id, message_text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
        return False

async def process_pending_messages():
    """Обрабатывает неотправленные сообщения"""
    with flask_app.app_context():
        pending_messages = AnonymousMessage.query.filter_by(is_sent=False).all()
        
        for msg in pending_messages:
            try:
                formatted_message = msg.get_formatted_message() if MODELS_V2_AVAILABLE else f"📩 Анонимное сообщение:\n\n{msg.message_text}"
                
                success = await send_message_to_user(
                    msg.recipient.telegram_id,
                    formatted_message
                )
                
                if success:
                    msg.is_sent = True
                    db.session.commit()
                    logger.info(f"Сообщение {msg.id} отправлено пользователю {msg.recipient.telegram_id}")
                
            except Exception as e:
                logger.error(f"Ошибка обработки сообщения {msg.id}: {e}")

async def periodic_message_processing():
    """Периодическая обработка сообщений"""
    while True:
        try:
            await process_pending_messages()
        except Exception as e:
            logger.error(f"Ошибка в периодической обработке: {e}")
        
        await asyncio.sleep(10)  # Проверяем каждые 10 секунд

async def main():
    """Главная функция бота"""
    if BOT_TOKEN == "dummy_token":
        logger.warning("Бот не запущен: отсутствует токен")
        return
    
    logger.info("Запуск Telegram-бота...")
    
    # Запускаем периодическую обработку сообщений
    asyncio.create_task(periodic_message_processing())
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

