import os
import sys
# DON'T CHANGE: Add the src directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template_string
from flask_cors import CORS
import threading
import asyncio

# Импортируем обновленные модели
try:
    from models.telegram_user_v2 import db, TelegramUser, AnonymousMessage, AdminSession, AdminAction, VIPMessageSettings
    MODELS_V2_AVAILABLE = True
except ImportError:
    from models.telegram_user import db, TelegramUser, AnonymousMessage
    MODELS_V2_AVAILABLE = False

# Импортируем маршруты
from routes.user import user_bp

# Импортируем обновленные маршруты
try:
    from routes.admin import admin_bp
    from routes.anonymous_v2 import anonymous_bp
    ADMIN_PANEL_AVAILABLE = True
except ImportError:
    from routes.anonymous import anonymous_bp
    ADMIN_PANEL_AVAILABLE = False

def create_app():
    app = Flask(__name__)
    
    # Конфигурация
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database/app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Инициализация расширений
    db.init_app(app)
    CORS(app)
    
    # Регистрация blueprints
    app.register_blueprint(user_bp)
    app.register_blueprint(anonymous_bp)
    
    if ADMIN_PANEL_AVAILABLE:
        app.register_blueprint(admin_bp)
    
    # Создание таблиц базы данных
    with app.app_context():
        # Создаем директорию для базы данных если её нет
        db_dir = os.path.dirname(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        db.create_all()
    
    @app.route('/')
    def index():
        """Главная страница"""
        
        # Собираем статистику
        stats = {
            'total_users': TelegramUser.query.count(),
            'total_messages': AnonymousMessage.query.count(),
        }
        
        if MODELS_V2_AVAILABLE:
            try:
                stats['vip_users'] = TelegramUser.query.filter_by(is_vip=True).count()
                stats['admin_users'] = TelegramUser.query.filter_by(is_admin=True).count()
            except:
                stats['vip_users'] = 0
                stats['admin_users'] = 0
        else:
            stats['vip_users'] = 0
            stats['admin_users'] = 0
        
        return render_template_string(INDEX_TEMPLATE, 
                                    stats=stats, 
                                    admin_panel_available=ADMIN_PANEL_AVAILABLE,
                                    models_v2_available=MODELS_V2_AVAILABLE)
    
    @app.route('/api/stats')
    def api_stats():
        """API для получения статистики"""
        stats = {
            'total_users': TelegramUser.query.count(),
            'total_messages': AnonymousMessage.query.count(),
            'sent_messages': AnonymousMessage.query.filter_by(is_sent=True).count(),
        }
        
        if MODELS_V2_AVAILABLE:
            try:
                stats['vip_users'] = TelegramUser.query.filter_by(is_vip=True).count()
                stats['admin_users'] = TelegramUser.query.filter_by(is_admin=True).count()
            except:
                stats['vip_users'] = 0
                stats['admin_users'] = 0
        else:
            stats['vip_users'] = 0
            stats['admin_users'] = 0
        
        stats['delivery_rate'] = round((stats['sent_messages'] / stats['total_messages'] * 100) if stats['total_messages'] > 0 else 0, 2)
        
        return stats
    
    return app

def run_telegram_bot():
    """Запуск Telegram-бота в отдельном потоке"""
    try:
        # Импортируем обновленный бот
        try:
            from telegram_bot_v2 import main as bot_main
        except ImportError:
            from telegram_bot import main as bot_main
        
        # Запускаем бота
        asyncio.run(bot_main())
    except Exception as e:
        print(f"Ошибка запуска Telegram-бота: {e}")
        print("Бот будет недоступен, но веб-интерфейс продолжит работать")

# HTML шаблон главной страницы
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Bot - Анонимные сообщения</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .hero-section {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 4rem 0;
        }
        .feature-card {
            transition: transform 0.3s ease;
            border: none;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .feature-card:hover {
            transform: translateY(-5px);
        }
        .stats-card {
            background: linear-gradient(45deg, #f093fb 0%, #f5576c 100%);
            color: white;
            border: none;
        }
        .admin-badge {
            background: linear-gradient(45deg, #ffd700, #ffed4e);
            color: #333;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <!-- Навигация -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-robot"></i> Telegram Bot
            </a>
            <div class="navbar-nav ms-auto">
                {% if admin_panel_available %}
                <a class="nav-link" href="/admin/login">
                    <i class="fas fa-cog"></i> Админ-панель
                </a>
                {% endif %}
            </div>
        </div>
    </nav>

    <!-- Главная секция -->
    <section class="hero-section">
        <div class="container text-center">
            <h1 class="display-4 mb-4">
                <i class="fas fa-paper-plane"></i>
                Анонимные сообщения
            </h1>
            <p class="lead mb-4">
                Получайте анонимные сообщения через Telegram-бота
                {% if models_v2_available %}
                с поддержкой VIP-функций
                {% endif %}
            </p>
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card bg-white text-dark">
                        <div class="card-body">
                            <h5>📊 Статистика системы</h5>
                            <div class="row text-center">
                                <div class="col-3">
                                    <h4 class="text-primary">{{ stats.total_users }}</h4>
                                    <small>Пользователей</small>
                                </div>
                                <div class="col-3">
                                    <h4 class="text-success">{{ stats.total_messages }}</h4>
                                    <small>Сообщений</small>
                                </div>
                                {% if models_v2_available %}
                                <div class="col-3">
                                    <h4 class="text-warning">{{ stats.vip_users }}</h4>
                                    <small>VIP</small>
                                </div>
                                <div class="col-3">
                                    <h4 class="text-danger">{{ stats.admin_users }}</h4>
                                    <small>Админов</small>
                                </div>
                                {% endif %}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Возможности -->
    <section class="py-5">
        <div class="container">
            <h2 class="text-center mb-5">🚀 Возможности</h2>
            <div class="row">
                <div class="col-md-4 mb-4">
                    <div class="card feature-card h-100">
                        <div class="card-body text-center">
                            <i class="fas fa-user-secret fa-3x text-primary mb-3"></i>
                            <h5>Полная анонимность</h5>
                            <p class="text-muted">
                                Отправляйте сообщения полностью анонимно. 
                                Получатель не узнает, кто отправил сообщение.
                            </p>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-4 mb-4">
                    <div class="card feature-card h-100">
                        <div class="card-body text-center">
                            <i class="fas fa-link fa-3x text-success mb-3"></i>
                            <h5>Уникальные ссылки</h5>
                            <p class="text-muted">
                                У каждого пользователя есть своя уникальная ссылка 
                                для получения анонимных сообщений.
                            </p>
                        </div>
                    </div>
                </div>
                
                {% if models_v2_available %}
                <div class="col-md-4 mb-4">
                    <div class="card feature-card h-100">
                        <div class="card-body text-center">
                            <i class="fas fa-star fa-3x text-warning mb-3"></i>
                            <h5>VIP-функции</h5>
                            <p class="text-muted">
                                VIP-пользователи могут получать неанонимные сообщения 
                                с именем и контактами отправителя.
                            </p>
                        </div>
                    </div>
                </div>
                {% else %}
                <div class="col-md-4 mb-4">
                    <div class="card feature-card h-100">
                        <div class="card-body text-center">
                            <i class="fas fa-telegram fa-3x text-info mb-3"></i>
                            <h5>Telegram интеграция</h5>
                            <p class="text-muted">
                                Сообщения доставляются мгновенно 
                                прямо в Telegram получателя.
                            </p>
                        </div>
                    </div>
                </div>
                {% endif %}
            </div>
        </div>
    </section>

    <!-- Как использовать -->
    <section class="py-5 bg-light">
        <div class="container">
            <h2 class="text-center mb-5">📝 Как использовать</h2>
            <div class="row">
                <div class="col-md-4 text-center mb-4">
                    <div class="mb-3">
                        <i class="fas fa-robot fa-3x text-primary"></i>
                    </div>
                    <h5>1. Запустите бота</h5>
                    <p class="text-muted">
                        Найдите бота в Telegram и нажмите /start 
                        для получения вашей уникальной ссылки.
                    </p>
                </div>
                
                <div class="col-md-4 text-center mb-4">
                    <div class="mb-3">
                        <i class="fas fa-share fa-3x text-success"></i>
                    </div>
                    <h5>2. Поделитесь ссылкой</h5>
                    <p class="text-muted">
                        Отправьте вашу уникальную ссылку друзьям, 
                        в социальные сети или разместите в профиле.
                    </p>
                </div>
                
                <div class="col-md-4 text-center mb-4">
                    <div class="mb-3">
                        <i class="fas fa-envelope fa-3x text-warning"></i>
                    </div>
                    <h5>3. Получайте сообщения</h5>
                    <p class="text-muted">
                        Все анонимные сообщения будут приходить 
                        к вам в Telegram автоматически.
                    </p>
                </div>
            </div>
        </div>
    </section>

    {% if admin_panel_available %}
    <!-- Админ-панель -->
    <section class="py-5">
        <div class="container">
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card">
                        <div class="card-body text-center">
                            <i class="fas fa-cog fa-3x text-primary mb-3"></i>
                            <h5>Админ-панель доступна</h5>
                            <p class="text-muted">
                                Система поддерживает админ-панель для управления пользователями, 
                                выдачи VIP-статуса и просмотра сообщений.
                            </p>
                            <a href="/admin/login" class="btn btn-primary">
                                <i class="fas fa-sign-in-alt"></i> Войти в админ-панель
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>
    {% endif %}

    <!-- Футер -->
    <footer class="bg-dark text-white py-4">
        <div class="container text-center">
            <p class="mb-0">
                <i class="fas fa-heart text-danger"></i>
                Создано с помощью Manus
            </p>
            <small class="text-muted">
                Версия: {% if models_v2_available %}2.0 (с админ-панелью){% else %}1.0{% endif %}
            </small>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

if __name__ == '__main__':
    app = create_app()
    
    # Запускаем Telegram-бота в отдельном потоке
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask-приложение
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

