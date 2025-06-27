import os
import sys
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, render_template_string, request, jsonify
from flask_cors import CORS
from src.models.telegram_user import db, TelegramUser, AnonymousMessage

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = 'asdf#FGSgvasgf$5$WGT'

# Включаем CORS для всех маршрутов
CORS(app)

# Настройка базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# HTML шаблон для формы отправки анонимного сообщения
SEND_MESSAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отправить анонимное сообщение</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #555;
        }
        textarea {
            width: 100%;
            min-height: 120px;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
            resize: vertical;
            box-sizing: border-box;
        }
        textarea:focus {
            outline: none;
            border-color: #007bff;
        }
        .btn {
            background-color: #007bff;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            width: 100%;
            transition: background-color 0.3s;
        }
        .btn:hover {
            background-color: #0056b3;
        }
        .btn:disabled {
            background-color: #ccc;
            cursor: not-allowed;
        }
        .info {
            background-color: #e7f3ff;
            border: 1px solid #b3d9ff;
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 20px;
            color: #0066cc;
        }
        .error {
            background-color: #ffe7e7;
            border: 1px solid #ffb3b3;
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 20px;
            color: #cc0000;
        }
        .success {
            background-color: #e7ffe7;
            border: 1px solid #b3ffb3;
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 20px;
            color: #006600;
        }
        .char-counter {
            text-align: right;
            font-size: 14px;
            color: #666;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📩 Отправить анонимное сообщение</h1>
        
        {% if error %}
        <div class="error">
            {{ error }}
        </div>
        {% endif %}
        
        {% if success %}
        <div class="success">
            ✅ Ваше анонимное сообщение успешно сохранено! (Демо-режим: сообщение не отправлено в Telegram)
        </div>
        {% else %}
        <div class="info">
            ℹ️ Демо-версия: Ваше сообщение будет сохранено в базе данных, но не отправлено в Telegram. Для полной функциональности необходимо настроить Telegram бота.
        </div>
        
        <form method="POST" id="messageForm">
            <div class="form-group">
                <label for="message">Ваше сообщение:</label>
                <textarea 
                    name="message" 
                    id="message" 
                    placeholder="Введите ваше анонимное сообщение здесь..."
                    maxlength="4000"
                    required
                ></textarea>
                <div class="char-counter">
                    <span id="charCount">0</span>/4000 символов
                </div>
            </div>
            
            <button type="submit" class="btn" id="submitBtn">
                Отправить анонимно (демо)
            </button>
        </form>
        {% endif %}
    </div>

    <script>
        const textarea = document.getElementById('message');
        const charCount = document.getElementById('charCount');
        const submitBtn = document.getElementById('submitBtn');
        const form = document.getElementById('messageForm');

        if (textarea) {
            textarea.addEventListener('input', function() {
                const count = this.value.length;
                charCount.textContent = count;
                
                if (count > 4000) {
                    charCount.style.color = '#cc0000';
                    submitBtn.disabled = true;
                } else {
                    charCount.style.color = '#666';
                    submitBtn.disabled = false;
                }
            });

            form.addEventListener('submit', function() {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Отправляется...';
            });
        }
    </script>
</body>
</html>
"""

@app.route('/send/<link_id>', methods=['GET', 'POST'])
def send_anonymous_message(link_id):
    """Страница для отправки анонимного сообщения (демо-версия)"""
    # Создаем демо-пользователя если его нет
    user = TelegramUser.query.filter_by(unique_link_id=link_id).first()
    
    if not user:
        # Создаем демо-пользователя для демонстрации
        user = TelegramUser(
            telegram_id=999999999,
            username="demo_user",
            first_name="Демо",
            last_name="Пользователь"
        )
        user.unique_link_id = link_id
        db.session.add(user)
        db.session.commit()
    
    if request.method == 'POST':
        message_text = request.form.get('message', '').strip()
        
        if not message_text:
            return render_template_string(SEND_MESSAGE_TEMPLATE, 
                                        error="Сообщение не может быть пустым.")
        
        if len(message_text) > 4000:
            return render_template_string(SEND_MESSAGE_TEMPLATE, 
                                        error="Сообщение слишком длинное. Максимум 4000 символов.")
        
        # Сохраняем сообщение в базу данных
        anonymous_message = AnonymousMessage(
            recipient_id=user.id,
            message_text=message_text,
            sender_ip=request.remote_addr
        )
        db.session.add(anonymous_message)
        db.session.commit()
        
        return render_template_string(SEND_MESSAGE_TEMPLATE, success=True)
    
    return render_template_string(SEND_MESSAGE_TEMPLATE)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API для получения статистики"""
    total_users = TelegramUser.query.count()
    total_messages = AnonymousMessage.query.count()
    sent_messages = AnonymousMessage.query.filter_by(is_sent=True).count()
    
    return jsonify({
        'total_users': total_users,
        'total_messages': total_messages,
        'sent_messages': sent_messages,
        'delivery_rate': round((sent_messages / total_messages * 100) if total_messages > 0 else 0, 2)
    })

with app.app_context():
    db.create_all()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

