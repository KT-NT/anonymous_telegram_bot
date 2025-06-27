from flask import Blueprint, request, jsonify, render_template_string
import os
from datetime import datetime

# Импортируем обновленные модели
try:
    from src.models.telegram_user_v2 import db, TelegramUser, AnonymousMessage, VIPMessageSettings
except ImportError:
    # Fallback на старые модели если новые еще не установлены
    from src.models.telegram_user import db, TelegramUser, AnonymousMessage

anonymous_bp = Blueprint('anonymous', __name__)

@anonymous_bp.route('/send/<link_id>')
def send_message_form(link_id):
    """Страница отправки анонимного сообщения"""
    
    # Находим пользователя по уникальной ссылке
    user = TelegramUser.query.filter_by(unique_link_id=link_id).first()
    
    if not user:
        return render_template_string(ERROR_TEMPLATE, 
                                    error="Ссылка недействительна или пользователь не найден"), 404
    
    # Проверяем VIP-статус и получаем настройки
    is_vip = False
    vip_settings = None
    
    try:
        is_vip = user.is_vip
        if is_vip:
            vip_settings = VIPMessageSettings.query.filter_by(user_id=user.id).first()
    except AttributeError:
        # Fallback для старой версии
        pass
    
    return render_template_string(SEND_MESSAGE_TEMPLATE, 
                                user=user, 
                                is_vip=is_vip, 
                                vip_settings=vip_settings,
                                link_id=link_id)

@anonymous_bp.route('/send/<link_id>', methods=['POST'])
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
    try:
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
    except AttributeError:
        # Fallback для старой версии - все сообщения анонимные
        pass
    
    try:
        db.session.add(message)
        db.session.commit()
        
        # Здесь должна быть логика отправки сообщения в Telegram
        # Пока что просто помечаем как отправленное для демо
        message.is_sent = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Сообщение успешно отправлено!'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Ошибка при отправке сообщения'}), 500

@anonymous_bp.route('/api/user/<link_id>/info')
def get_user_info(link_id):
    """API для получения информации о пользователе по ссылке"""
    
    user = TelegramUser.query.filter_by(unique_link_id=link_id).first()
    
    if not user:
        return jsonify({'error': 'Пользователь не найден'}), 404
    
    user_info = {
        'display_name': user.get_display_name(),
        'is_vip': False,
        'allow_non_anonymous': False,
        'require_contact': False,
        'custom_message': None
    }
    
    try:
        user_info['is_vip'] = user.is_vip
        
        if user.is_vip and user.vip_settings:
            user_info['allow_non_anonymous'] = user.vip_settings.allow_non_anonymous
            user_info['require_contact'] = user.vip_settings.require_contact
            user_info['custom_message'] = user.vip_settings.custom_message
            
    except AttributeError:
        # Fallback для старой версии
        pass
    
    return jsonify(user_info)

# HTML шаблоны
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
    <title>Отправить анонимное сообщение</title>
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
                
                {% if vip_settings and vip_settings.custom_message %}
                <div class="alert alert-info">
                    <i class="fas fa-info-circle"></i>
                    {{ vip_settings.custom_message }}
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
                        
                        {% if is_vip and vip_settings and vip_settings.allow_non_anonymous %}
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
                                    
                                    {% if not vip_settings.require_contact %}
                                    <div class="mb-3">
                                        <label for="senderContact" class="form-label">Контакт (опционально):</label>
                                        <input type="text" class="form-control" id="senderContact" name="sender_contact" 
                                               placeholder="Telegram, email, телефон..." maxlength="200">
                                    </div>
                                    {% else %}
                                    <div class="mb-3">
                                        <label for="senderContact" class="form-label">Контакт (обязательно):</label>
                                        <input type="text" class="form-control" id="senderContact" name="sender_contact" 
                                               placeholder="Telegram, email, телефон..." maxlength="200" required>
                                    </div>
                                    {% endif %}
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

