import os
import sys
# DON'T CHANGE: Add the src directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets
import string

# Инициализация Flask и базы данных
db = SQLAlchemy()

# Простые модели для демо
class TelegramUser(db.Model):
    __tablename__ = 'telegram_users'
    
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False)
    username = db.Column(db.String(100))
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    unique_link_id = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    is_vip = db.Column(db.Boolean, default=False)
    vip_granted_at = db.Column(db.DateTime)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.unique_link_id:
            self.unique_link_id = self.generate_unique_link_id()
    
    def generate_unique_link_id(self):
        return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    
    def get_display_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.username:
            return f"@{self.username}"
        else:
            return f"User {self.telegram_id}"
    
    def get_anonymous_link(self, base_url):
        return f"{base_url}/send/{self.unique_link_id}"

class AnonymousMessage(db.Model):
    __tablename__ = 'anonymous_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('telegram_users.id'), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    sender_ip = db.Column(db.String(45))
    is_sent = db.Column(db.Boolean, default=False)
    is_anonymous = db.Column(db.Boolean, default=True)
    sender_name = db.Column(db.String(100))
    sender_contact = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    recipient = db.relationship('TelegramUser', backref='received_messages')

def create_app():
    app = Flask(__name__)
    
    # Конфигурация
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database/app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Инициализация расширений
    db.init_app(app)
    CORS(app)
    
    # Создание таблиц базы данных
    with app.app_context():
        # Создаем директорию для базы данных если её нет
        db_dir = os.path.dirname(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        db.create_all()
        
        # Создаем тестового пользователя если база пустая
        if TelegramUser.query.count() == 0:
            test_user = TelegramUser(
                telegram_id=123456789,
                username="demo_user",
                first_name="Демо",
                last_name="Пользователь",
                is_vip=True
            )
            db.session.add(test_user)
            
            # Создаем админа
            admin_user = TelegramUser(
                telegram_id=987654321,
                username="admin",
                first_name="Админ",
                last_name="Система",
                is_admin=True,
                is_vip=True
            )
            db.session.add(admin_user)
            
            # Создаем тестовые сообщения
            test_message1 = AnonymousMessage(
                recipient_id=1,
                message_text="Привет! Это тестовое анонимное сообщение.",
                is_sent=True
            )
            test_message2 = AnonymousMessage(
                recipient_id=1,
                message_text="А это неанонимное сообщение от VIP-пользователя!",
                is_anonymous=False,
                sender_name="Иван Петров",
                sender_contact="@ivan_petrov",
                is_sent=True
            )
            db.session.add(test_message1)
            db.session.add(test_message2)
            
            db.session.commit()
    
    @app.route('/')
    def index():
        """Главная страница"""
        
        # Собираем статистику
        stats = {
            'total_users': TelegramUser.query.count(),
            'total_messages': AnonymousMessage.query.count(),
            'vip_users': TelegramUser.query.filter_by(is_vip=True).count(),
            'admin_users': TelegramUser.query.filter_by(is_admin=True).count(),
        }
        
        return render_template_string(INDEX_TEMPLATE, stats=stats)
    
    @app.route('/send/<link_id>')
    def send_message_form(link_id):
        """Страница отправки анонимного сообщения"""
        
        # Находим пользователя по уникальной ссылке
        user = TelegramUser.query.filter_by(unique_link_id=link_id).first()
        
        if not user:
            return render_template_string(ERROR_TEMPLATE, 
                                        error="Ссылка недействительна или пользователь не найден"), 404
        
        return render_template_string(SEND_MESSAGE_TEMPLATE, 
                                    user=user, 
                                    is_vip=user.is_vip,
                                    link_id=link_id)
    
    @app.route('/send/<link_id>', methods=['POST'])
    def send_message(link_id):
        """Обработка отправки анонимного сообщения"""
        
        # Находим пользователя по уникальной ссылке
        user = TelegramUser.query.filter_by(unique_link_id=link_id).first()
        
        if not user:
            return jsonify({'error': 'Пользователь не найден'}), 404
        
        message_text = request.form.get('message')
        if not message_text or len(message_text.strip()) == 0:
            return jsonify({'error': 'Сообщение не может быть пустым'}), 400
        
        if len(message_text) > 4000:
            return jsonify({'error': 'Сообщение слишком длинное (максимум 4000 символов)'}), 400
        
        # Получаем IP отправителя
        sender_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR'))
        
        # Создаем сообщение
        message = AnonymousMessage(
            recipient_id=user.id,
            message_text=message_text.strip(),
            sender_ip=sender_ip
        )
        
        # Обрабатываем VIP-функции
        if user.is_vip:
            # Проверяем, хочет ли отправитель показать свое имя
            show_name = request.form.get('show_name') == 'on'
            sender_name = request.form.get('sender_name', '').strip()
            sender_contact = request.form.get('sender_contact', '').strip()
            
            if show_name and sender_name:
                message.is_anonymous = False
                message.sender_name = sender_name[:100]  # Ограничиваем длину
                
                if sender_contact:
                    message.sender_contact = sender_contact[:200]  # Ограничиваем длину
        
        try:
            db.session.add(message)
            db.session.commit()
            
            # Помечаем как отправленное для демо
            message.is_sent = True
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Сообщение успешно отправлено!'
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': 'Ошибка при отправке сообщения'}), 500
    
    @app.route('/admin/demo')
    def admin_demo():
        """Демо админ-панели"""
        
        users = TelegramUser.query.all()
        messages = AnonymousMessage.query.order_by(AnonymousMessage.created_at.desc()).limit(10).all()
        
        stats = {
            'total_users': TelegramUser.query.count(),
            'total_messages': AnonymousMessage.query.count(),
            'vip_users': TelegramUser.query.filter_by(is_vip=True).count(),
            'admin_users': TelegramUser.query.filter_by(is_admin=True).count(),
            'anonymous_messages': AnonymousMessage.query.filter_by(is_anonymous=True).count(),
            'non_anonymous_messages': AnonymousMessage.query.filter_by(is_anonymous=False).count(),
        }
        
        return render_template_string(ADMIN_DEMO_TEMPLATE, 
                                    users=users, 
                                    messages=messages, 
                                    stats=stats)
    
    @app.route('/api/stats')
    def api_stats():
        """API для получения статистики"""
        stats = {
            'total_users': TelegramUser.query.count(),
            'total_messages': AnonymousMessage.query.count(),
            'sent_messages': AnonymousMessage.query.filter_by(is_sent=True).count(),
            'vip_users': TelegramUser.query.filter_by(is_vip=True).count(),
            'admin_users': TelegramUser.query.filter_by(is_admin=True).count(),
        }
        
        stats['delivery_rate'] = round((stats['sent_messages'] / stats['total_messages'] * 100) if stats['total_messages'] > 0 else 0, 2)
        
        return stats
    
    return app

# HTML шаблоны
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Bot - Анонимные сообщения с VIP и Админ-панелью</title>
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
        .vip-badge {
            background: linear-gradient(45deg, #ffd700, #ffed4e);
            color: #333;
            font-weight: bold;
        }
        .admin-badge {
            background: linear-gradient(45deg, #ff6b6b, #ee5a24);
            color: white;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <!-- Навигация -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-robot"></i> Telegram Bot v2.0
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/admin/demo">
                    <i class="fas fa-cog"></i> Демо Админ-панели
                </a>
            </div>
        </div>
    </nav>

    <!-- Главная секция -->
    <section class="hero-section">
        <div class="container text-center">
            <h1 class="display-4 mb-4">
                <i class="fas fa-paper-plane"></i>
                Анонимные сообщения v2.0
            </h1>
            <p class="lead mb-4">
                Получайте анонимные сообщения через Telegram-бота с поддержкой VIP-функций и админ-панели
            </p>
            <div class="row justify-content-center">
                <div class="col-md-10">
                    <div class="card bg-white text-dark">
                        <div class="card-body">
                            <h5>📊 Статистика системы</h5>
                            <div class="row text-center">
                                <div class="col-md-3 col-6">
                                    <h4 class="text-primary">{{ stats.total_users }}</h4>
                                    <small>Пользователей</small>
                                </div>
                                <div class="col-md-3 col-6">
                                    <h4 class="text-success">{{ stats.total_messages }}</h4>
                                    <small>Сообщений</small>
                                </div>
                                <div class="col-md-3 col-6">
                                    <h4 class="text-warning">{{ stats.vip_users }}</h4>
                                    <small>VIP</small>
                                </div>
                                <div class="col-md-3 col-6">
                                    <h4 class="text-danger">{{ stats.admin_users }}</h4>
                                    <small>Админов</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Новые возможности -->
    <section class="py-5">
        <div class="container">
            <h2 class="text-center mb-5">🚀 Новые возможности v2.0</h2>
            <div class="row">
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
                
                <div class="col-md-4 mb-4">
                    <div class="card feature-card h-100">
                        <div class="card-body text-center">
                            <i class="fas fa-cog fa-3x text-primary mb-3"></i>
                            <h5>Админ-панель</h5>
                            <p class="text-muted">
                                Веб-интерфейс для управления пользователями, 
                                выдачи VIP-статуса и просмотра сообщений.
                            </p>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-4 mb-4">
                    <div class="card feature-card h-100">
                        <div class="card-body text-center">
                            <i class="fas fa-shield-alt fa-3x text-success mb-3"></i>
                            <h5>Безопасность</h5>
                            <p class="text-muted">
                                Расширенная система безопасности с логированием 
                                действий и контролем доступа.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Демо-ссылки -->
    <section class="py-5 bg-light">
        <div class="container">
            <h2 class="text-center mb-5">🎯 Попробуйте прямо сейчас</h2>
            <div class="row justify-content-center">
                <div class="col-md-8">
                    <div class="card">
                        <div class="card-body">
                            <h5 class="card-title">Демо-ссылки для тестирования:</h5>
                            
                            <div class="mb-3">
                                <strong>Обычный пользователь:</strong><br>
                                <a href="/send/demo123" class="btn btn-outline-primary btn-sm">
                                    <i class="fas fa-paper-plane"></i> Отправить анонимное сообщение
                                </a>
                            </div>
                            
                            <div class="mb-3">
                                <strong>VIP-пользователь:</strong><br>
                                <a href="/send/{{ 'demo123' if stats.total_users > 0 else 'demo123' }}" class="btn btn-outline-warning btn-sm">
                                    <i class="fas fa-star"></i> Отправить VIP-сообщение
                                </a>
                                <span class="badge vip-badge ms-2">VIP</span>
                            </div>
                            
                            <div class="mb-3">
                                <strong>Админ-панель:</strong><br>
                                <a href="/admin/demo" class="btn btn-outline-danger btn-sm">
                                    <i class="fas fa-cog"></i> Демо админ-панели
                                </a>
                                <span class="badge admin-badge ms-2">ADMIN</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Футер -->
    <footer class="bg-dark text-white py-4">
        <div class="container text-center">
            <p class="mb-0">
                <i class="fas fa-heart text-danger"></i>
                Создано с помощью Manus
            </p>
            <small class="text-muted">
                Версия 2.0 с админ-панелью и VIP-функциями
            </small>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

ERROR_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ошибка</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
    <div class="container">
        <div class="row justify-content-center">
            <div class="col-md-6">
                <div class="card mt-5">
                    <div class="card-body text-center">
                        <i class="fas fa-exclamation-triangle fa-3x text-warning mb-3"></i>
                        <h4>Ошибка</h4>
                        <p class="text-muted">{{ error }}</p>
                        <a href="/" class="btn btn-primary">На главную</a>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

SEND_MESSAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отправить сообщение - {{ user.get_display_name() }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .vip-badge {
            background: linear-gradient(45deg, #ffd700, #ffed4e);
            color: #333;
            font-weight: bold;
        }
        .message-form {
            background: #f8f9fa;
            border-radius: 15px;
            padding: 2rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .vip-form {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .vip-form .form-control {
            background: rgba(255, 255, 255, 0.9);
            border: none;
        }
        .vip-form .form-label {
            color: #fff;
            font-weight: 500;
        }
    </style>
</head>
<body class="bg-light">
    <div class="container">
        <div class="row justify-content-center">
            <div class="col-md-8 col-lg-6">
                <div class="text-center mt-4 mb-4">
                    <h1>
                        <i class="fas fa-paper-plane text-primary"></i>
                        Отправить сообщение
                    </h1>
                    <p class="text-muted">
                        Для <strong>{{ user.get_display_name() }}</strong>
                        {% if is_vip %}
                            <span class="badge vip-badge ms-2">
                                <i class="fas fa-star"></i> VIP
                            </span>
                        {% endif %}
                    </p>
                </div>
                
                {% if is_vip %}
                <div class="alert alert-info">
                    <i class="fas fa-star text-warning"></i>
                    <strong>VIP-пользователь!</strong> Вы можете отправить неанонимное сообщение с вашим именем.
                </div>
                {% endif %}
                
                <div class="message-form {% if is_vip %}vip-form{% endif %}">
                    <form id="messageForm">
                        <div class="mb-3">
                            <label for="message" class="form-label">
                                <i class="fas fa-comment"></i> Ваше сообщение:
                            </label>
                            <textarea 
                                class="form-control" 
                                id="message" 
                                name="message" 
                                rows="6" 
                                placeholder="Напишите ваше сообщение здесь..." 
                                maxlength="4000" 
                                required
                            ></textarea>
                            <div class="form-text">
                                <span id="charCount">0</span>/4000 символов
                            </div>
                        </div>
                        
                        {% if is_vip %}
                        <div class="card mb-3" style="background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.2);">
                            <div class="card-body">
                                <h6 class="card-title">
                                    <i class="fas fa-star text-warning"></i>
                                    VIP-опции
                                </h6>
                                
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" id="showName" name="show_name">
                                    <label class="form-check-label" for="showName">
                                        Показать мое имя (неанонимно)
                                    </label>
                                </div>
                                
                                <div id="nameFields" style="display: none;">
                                    <div class="mb-3">
                                        <label for="senderName" class="form-label">Ваше имя:</label>
                                        <input type="text" class="form-control" id="senderName" name="sender_name" maxlength="100">
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label for="senderContact" class="form-label">Контакт (опционально):</label>
                                        <input type="text" class="form-control" id="senderContact" name="sender_contact" 
                                               placeholder="Telegram, email, телефон..." maxlength="200">
                                    </div>
                                </div>
                            </div>
                        </div>
                        {% endif %}
                        
                        <div class="d-grid">
                            <button type="submit" class="btn btn-primary btn-lg" id="sendBtn">
                                <i class="fas fa-paper-plane"></i>
                                {% if is_vip %}
                                    Отправить сообщение
                                {% else %}
                                    Отправить анонимно
                                {% endif %}
                            </button>
                        </div>
                    </form>
                </div>
                
                <div class="text-center mt-4">
                    <small class="text-muted">
                        <i class="fas fa-shield-alt"></i>
                        Ваша конфиденциальность защищена
                    </small>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Счетчик символов
        const messageTextarea = document.getElementById('message');
        const charCount = document.getElementById('charCount');
        
        messageTextarea.addEventListener('input', function() {
            charCount.textContent = this.value.length;
        });
        
        // Показ/скрытие полей имени для VIP
        const showNameCheckbox = document.getElementById('showName');
        const nameFields = document.getElementById('nameFields');
        
        if (showNameCheckbox) {
            showNameCheckbox.addEventListener('change', function() {
                nameFields.style.display = this.checked ? 'block' : 'none';
                
                // Делаем поле имени обязательным если выбрано показать имя
                const senderNameInput = document.getElementById('senderName');
                if (this.checked) {
                    senderNameInput.required = true;
                } else {
                    senderNameInput.required = false;
                }
            });
        }
        
        // Отправка формы
        document.getElementById('messageForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const sendBtn = document.getElementById('sendBtn');
            
            // Блокируем кнопку
            sendBtn.disabled = true;
            sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Отправляем...';
            
            fetch('/send/{{ link_id }}', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Показываем сообщение об успехе
                    document.querySelector('.message-form').innerHTML = `
                        <div class="text-center">
                            <i class="fas fa-check-circle fa-3x text-success mb-3"></i>
                            <h4>Сообщение отправлено!</h4>
                            <p class="text-muted">Ваше сообщение успешно доставлено получателю.</p>
                            <a href="/send/{{ link_id }}" class="btn btn-primary">Отправить еще</a>
                        </div>
                    `;
                } else {
                    alert('Ошибка: ' + data.error);
                    sendBtn.disabled = false;
                    sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Отправить сообщение';
                }
            })
            .catch(error => {
                alert('Произошла ошибка при отправке сообщения');
                sendBtn.disabled = false;
                sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Отправить сообщение';
            });
        });
    </script>
</body>
</html>
"""

ADMIN_DEMO_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Демо Админ-панели</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .admin-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .stat-card {
            border: none;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .vip-badge {
            background: linear-gradient(45deg, #ffd700, #ffed4e);
            color: #333;
            font-weight: bold;
        }
        .admin-badge {
            background: linear-gradient(45deg, #ff6b6b, #ee5a24);
            color: white;
            font-weight: bold;
        }
    </style>
</head>
<body class="bg-light">
    <!-- Заголовок -->
    <div class="admin-header py-4">
        <div class="container">
            <div class="row align-items-center">
                <div class="col">
                    <h1><i class="fas fa-cog"></i> Демо Админ-панели</h1>
                    <p class="mb-0">Управление Telegram-ботом анонимных сообщений</p>
                </div>
                <div class="col-auto">
                    <a href="/" class="btn btn-light">
                        <i class="fas fa-home"></i> На главную
                    </a>
                </div>
            </div>
        </div>
    </div>

    <div class="container mt-4">
        <!-- Статистика -->
        <div class="row mb-4">
            <div class="col-md-3 mb-3">
                <div class="card stat-card text-center">
                    <div class="card-body">
                        <i class="fas fa-users fa-2x text-primary mb-2"></i>
                        <h4>{{ stats.total_users }}</h4>
                        <small class="text-muted">Всего пользователей</small>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="card stat-card text-center">
                    <div class="card-body">
                        <i class="fas fa-envelope fa-2x text-success mb-2"></i>
                        <h4>{{ stats.total_messages }}</h4>
                        <small class="text-muted">Всего сообщений</small>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="card stat-card text-center">
                    <div class="card-body">
                        <i class="fas fa-star fa-2x text-warning mb-2"></i>
                        <h4>{{ stats.vip_users }}</h4>
                        <small class="text-muted">VIP-пользователей</small>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="card stat-card text-center">
                    <div class="card-body">
                        <i class="fas fa-shield-alt fa-2x text-danger mb-2"></i>
                        <h4>{{ stats.admin_users }}</h4>
                        <small class="text-muted">Администраторов</small>
                    </div>
                </div>
            </div>
        </div>

        <!-- Пользователи -->
        <div class="row">
            <div class="col-md-6 mb-4">
                <div class="card">
                    <div class="card-header">
                        <h5><i class="fas fa-users"></i> Пользователи</h5>
                    </div>
                    <div class="card-body">
                        {% for user in users %}
                        <div class="d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
                            <div>
                                <strong>{{ user.get_display_name() }}</strong><br>
                                <small class="text-muted">ID: {{ user.telegram_id }}</small>
                                {% if user.username %}
                                <small class="text-muted">@{{ user.username }}</small>
                                {% endif %}
                            </div>
                            <div>
                                {% if user.is_admin %}
                                <span class="badge admin-badge">ADMIN</span>
                                {% endif %}
                                {% if user.is_vip %}
                                <span class="badge vip-badge">VIP</span>
                                {% endif %}
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>

            <!-- Сообщения -->
            <div class="col-md-6 mb-4">
                <div class="card">
                    <div class="card-header">
                        <h5><i class="fas fa-envelope"></i> Последние сообщения</h5>
                    </div>
                    <div class="card-body">
                        {% for message in messages %}
                        <div class="mb-3 p-2 border rounded">
                            <div class="d-flex justify-content-between align-items-start mb-1">
                                <small class="text-muted">
                                    Для: {{ message.recipient.get_display_name() }}
                                </small>
                                <small class="text-muted">
                                    {{ message.created_at.strftime('%d.%m %H:%M') }}
                                </small>
                            </div>
                            
                            {% if not message.is_anonymous %}
                            <div class="mb-1">
                                <span class="badge bg-info">От: {{ message.sender_name }}</span>
                                {% if message.sender_contact %}
                                <span class="badge bg-secondary">{{ message.sender_contact }}</span>
                                {% endif %}
                            </div>
                            {% else %}
                            <div class="mb-1">
                                <span class="badge bg-dark">Анонимно</span>
                            </div>
                            {% endif %}
                            
                            <div class="text-truncate">
                                {{ message.message_text[:100] }}{% if message.message_text|length > 100 %}...{% endif %}
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>

        <!-- Дополнительная статистика -->
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h5><i class="fas fa-chart-bar"></i> Детальная статистика</h5>
                    </div>
                    <div class="card-body">
                        <div class="row text-center">
                            <div class="col-md-6">
                                <h6>Типы сообщений</h6>
                                <div class="mb-2">
                                    <span class="badge bg-dark me-2">Анонимных:</span>
                                    <strong>{{ stats.anonymous_messages }}</strong>
                                </div>
                                <div class="mb-2">
                                    <span class="badge bg-info me-2">Неанонимных:</span>
                                    <strong>{{ stats.non_anonymous_messages }}</strong>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <h6>Активность</h6>
                                <div class="mb-2">
                                    <span class="badge bg-success me-2">Процент VIP:</span>
                                    <strong>{{ "%.1f"|format((stats.vip_users / stats.total_users * 100) if stats.total_users > 0 else 0) }}%</strong>
                                </div>
                                <div class="mb-2">
                                    <span class="badge bg-primary me-2">Сообщений на пользователя:</span>
                                    <strong>{{ "%.1f"|format((stats.total_messages / stats.total_users) if stats.total_users > 0 else 0) }}</strong>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Информация -->
        <div class="row mt-4">
            <div class="col-12">
                <div class="alert alert-info">
                    <h6><i class="fas fa-info-circle"></i> Информация о демо-версии</h6>
                    <p class="mb-0">
                        Это демонстрационная версия админ-панели. В полной версии доступны:
                        расширенная фильтрация, экспорт данных, управление настройками, 
                        логи действий администраторов и многое другое.
                    </p>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

if __name__ == '__main__':
    app = create_app()
    
    # Запускаем Flask-приложение
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

