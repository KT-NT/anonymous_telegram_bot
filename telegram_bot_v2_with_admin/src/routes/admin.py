from flask import Blueprint, request, jsonify, render_template_string, session, redirect, url_for
from functools import wraps
import os
from datetime import datetime, timedelta

# Импортируем обновленные модели
try:
    from src.models.telegram_user_v2 import db, TelegramUser, AnonymousMessage, AdminSession, AdminAction, VIPMessageSettings
except ImportError:
    # Fallback на старые модели если новые еще не установлены
    from src.models.telegram_user import db, TelegramUser, AnonymousMessage

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Список администраторов (Telegram ID)
ADMIN_TELEGRAM_IDS = [
    # Добавьте сюда Telegram ID администраторов
    # 123456789,
    # 987654321,
]

def admin_required(f):
    """Декоратор для проверки прав администратора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Проверяем токен сессии
        session_token = request.headers.get('Authorization') or session.get('admin_token')
        
        if not session_token:
            return jsonify({'error': 'Требуется аутентификация'}), 401
        
        try:
            admin_session = AdminSession.query.filter_by(
                session_token=session_token,
                is_active=True
            ).first()
            
            if not admin_session or not admin_session.is_valid():
                return jsonify({'error': 'Недействительная сессия'}), 401
            
            # Добавляем информацию об администраторе в request
            request.admin = admin_session.admin
            
        except Exception as e:
            # Fallback для старой версии без AdminSession
            return jsonify({'error': 'Система аутентификации недоступна'}), 503
        
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа для администраторов"""
    
    if request.method == 'GET':
        return render_template_string(LOGIN_TEMPLATE)
    
    # POST запрос - обработка входа
    telegram_id = request.form.get('telegram_id')
    
    if not telegram_id:
        return render_template_string(LOGIN_TEMPLATE, error="Введите Telegram ID")
    
    try:
        telegram_id = int(telegram_id)
    except ValueError:
        return render_template_string(LOGIN_TEMPLATE, error="Неверный формат Telegram ID")
    
    # Проверяем, является ли пользователь администратором
    user = TelegramUser.query.filter_by(telegram_id=telegram_id).first()
    
    if not user:
        return render_template_string(LOGIN_TEMPLATE, error="Пользователь не найден")
    
    # Проверяем права администратора
    is_admin = False
    try:
        is_admin = user.is_admin
    except AttributeError:
        # Fallback для старой версии - проверяем по списку
        is_admin = telegram_id in ADMIN_TELEGRAM_IDS
    
    if not is_admin:
        return render_template_string(LOGIN_TEMPLATE, error="Недостаточно прав доступа")
    
    # Создаем сессию администратора
    try:
        admin_session = AdminSession(admin_id=user.id)
        db.session.add(admin_session)
        db.session.commit()
        
        # Сохраняем токен в сессии
        session['admin_token'] = admin_session.session_token
        session['admin_id'] = user.id
        
        return redirect(url_for('admin.dashboard'))
        
    except Exception as e:
        # Fallback для старой версии
        session['admin_id'] = user.id
        session['admin_token'] = 'legacy_session'
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/logout', methods=['POST'])
def logout():
    """Выход из админ-панели"""
    session_token = session.get('admin_token')
    
    if session_token:
        try:
            admin_session = AdminSession.query.filter_by(session_token=session_token).first()
            if admin_session:
                admin_session.invalidate()
                db.session.commit()
        except:
            pass
    
    session.clear()
    return redirect(url_for('admin.login'))

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Главная страница админ-панели"""
    
    # Собираем статистику
    stats = {
        'total_users': TelegramUser.query.count(),
        'total_messages': AnonymousMessage.query.count(),
        'sent_messages': AnonymousMessage.query.filter_by(is_sent=True).count(),
    }
    
    try:
        stats['vip_users'] = TelegramUser.query.filter_by(is_vip=True).count()
        stats['admin_users'] = TelegramUser.query.filter_by(is_admin=True).count()
        
        # Статистика за последние 24 часа
        yesterday = datetime.utcnow() - timedelta(days=1)
        stats['new_users_24h'] = TelegramUser.query.filter(TelegramUser.created_at >= yesterday).count()
        stats['new_messages_24h'] = AnonymousMessage.query.filter(AnonymousMessage.created_at >= yesterday).count()
        
        # Последние действия администраторов
        recent_actions = AdminAction.query.order_by(AdminAction.created_at.desc()).limit(10).all()
        stats['recent_actions'] = [action.to_dict() for action in recent_actions]
        
    except Exception as e:
        # Fallback для старой версии
        stats['vip_users'] = 0
        stats['admin_users'] = len(ADMIN_TELEGRAM_IDS)
        stats['new_users_24h'] = 0
        stats['new_messages_24h'] = 0
        stats['recent_actions'] = []
    
    stats['delivery_rate'] = round((stats['sent_messages'] / stats['total_messages'] * 100) if stats['total_messages'] > 0 else 0, 2)
    
    return render_template_string(DASHBOARD_TEMPLATE, stats=stats, admin=request.admin)

@admin_bp.route('/users')
@admin_required
def users():
    """Страница управления пользователями"""
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    query = TelegramUser.query
    
    if search:
        query = query.filter(
            (TelegramUser.first_name.contains(search)) |
            (TelegramUser.last_name.contains(search)) |
            (TelegramUser.username.contains(search))
        )
    
    users = query.order_by(TelegramUser.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template_string(USERS_TEMPLATE, users=users, search=search, admin=request.admin)

@admin_bp.route('/users/<int:user_id>/grant_vip', methods=['POST'])
@admin_required
def grant_vip(user_id):
    """Выдача VIP-статуса пользователю"""
    
    user = TelegramUser.query.get_or_404(user_id)
    
    try:
        user.grant_vip(request.admin)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'VIP-статус выдан пользователю {user.get_display_name()}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Ошибка: {str(e)}'
        }), 400

@admin_bp.route('/users/<int:user_id>/revoke_vip', methods=['POST'])
@admin_required
def revoke_vip(user_id):
    """Отзыв VIP-статуса у пользователя"""
    
    user = TelegramUser.query.get_or_404(user_id)
    
    try:
        user.revoke_vip(request.admin)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'VIP-статус отозван у пользователя {user.get_display_name()}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Ошибка: {str(e)}'
        }), 400

@admin_bp.route('/messages')
@admin_required
def messages():
    """Страница просмотра сообщений"""
    
    page = request.args.get('page', 1, type=int)
    user_id = request.args.get('user_id', type=int)
    show_anonymous = request.args.get('anonymous', 'all')
    
    query = AnonymousMessage.query
    
    if user_id:
        query = query.filter_by(recipient_id=user_id)
    
    if show_anonymous == 'yes':
        query = query.filter_by(is_anonymous=True)
    elif show_anonymous == 'no':
        query = query.filter_by(is_anonymous=False)
    
    messages = query.order_by(AnonymousMessage.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Получаем список пользователей для фильтра
    users = TelegramUser.query.order_by(TelegramUser.first_name).all()
    
    return render_template_string(MESSAGES_TEMPLATE, 
                                messages=messages, 
                                users=users, 
                                selected_user_id=user_id,
                                show_anonymous=show_anonymous,
                                admin=request.admin)

@admin_bp.route('/logs')
@admin_required
def logs():
    """Страница логов действий администраторов"""
    
    page = request.args.get('page', 1, type=int)
    action_type = request.args.get('action_type', '')
    
    try:
        query = AdminAction.query
        
        if action_type:
            query = query.filter_by(action_type=action_type)
        
        actions = query.order_by(AdminAction.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        # Получаем типы действий для фильтра
        action_types = db.session.query(AdminAction.action_type).distinct().all()
        action_types = [at[0] for at in action_types]
        
    except Exception as e:
        # Fallback для старой версии
        actions = None
        action_types = []
    
    return render_template_string(LOGS_TEMPLATE, 
                                actions=actions, 
                                action_types=action_types,
                                selected_action_type=action_type,
                                admin=request.admin)

@admin_bp.route('/api/stats')
@admin_required
def api_stats():
    """API для получения статистики в реальном времени"""
    
    stats = {
        'total_users': TelegramUser.query.count(),
        'total_messages': AnonymousMessage.query.count(),
        'sent_messages': AnonymousMessage.query.filter_by(is_sent=True).count(),
    }
    
    try:
        stats['vip_users'] = TelegramUser.query.filter_by(is_vip=True).count()
        stats['admin_users'] = TelegramUser.query.filter_by(is_admin=True).count()
    except:
        stats['vip_users'] = 0
        stats['admin_users'] = len(ADMIN_TELEGRAM_IDS)
    
    stats['delivery_rate'] = round((stats['sent_messages'] / stats['total_messages'] * 100) if stats['total_messages'] > 0 else 0, 2)
    
    return jsonify(stats)

# HTML шаблоны
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Вход в админ-панель</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
    <div class="container">
        <div class="row justify-content-center">
            <div class="col-md-6 col-lg-4">
                <div class="card mt-5">
                    <div class="card-header text-center">
                        <h4>🔐 Админ-панель</h4>
                        <p class="text-muted">Telegram Bot</p>
                    </div>
                    <div class="card-body">
                        {% if error %}
                        <div class="alert alert-danger">{{ error }}</div>
                        {% endif %}
                        
                        <form method="POST">
                            <div class="mb-3">
                                <label for="telegram_id" class="form-label">Telegram ID</label>
                                <input type="number" class="form-control" id="telegram_id" name="telegram_id" required>
                                <div class="form-text">Введите ваш Telegram ID для входа</div>
                            </div>
                            <button type="submit" class="btn btn-primary w-100">Войти</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Админ-панель - Дашборд</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/admin/dashboard">
                <i class="fas fa-robot"></i> Админ-панель
            </a>
            <div class="navbar-nav ms-auto">
                <span class="navbar-text me-3">
                    Привет, {{ admin.get_display_name() }}!
                </span>
                <form method="POST" action="/admin/logout" class="d-inline">
                    <button type="submit" class="btn btn-outline-light btn-sm">Выйти</button>
                </form>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row">
            <div class="col-md-3">
                <div class="list-group">
                    <a href="/admin/dashboard" class="list-group-item list-group-item-action active">
                        <i class="fas fa-tachometer-alt"></i> Дашборд
                    </a>
                    <a href="/admin/users" class="list-group-item list-group-item-action">
                        <i class="fas fa-users"></i> Пользователи
                    </a>
                    <a href="/admin/messages" class="list-group-item list-group-item-action">
                        <i class="fas fa-envelope"></i> Сообщения
                    </a>
                    <a href="/admin/logs" class="list-group-item list-group-item-action">
                        <i class="fas fa-history"></i> Логи
                    </a>
                </div>
            </div>
            
            <div class="col-md-9">
                <h2>📊 Статистика системы</h2>
                
                <div class="row mb-4">
                    <div class="col-md-3">
                        <div class="card text-white bg-primary">
                            <div class="card-body">
                                <div class="d-flex justify-content-between">
                                    <div>
                                        <h4>{{ stats.total_users }}</h4>
                                        <p>Пользователей</p>
                                    </div>
                                    <i class="fas fa-users fa-2x"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-3">
                        <div class="card text-white bg-success">
                            <div class="card-body">
                                <div class="d-flex justify-content-between">
                                    <div>
                                        <h4>{{ stats.total_messages }}</h4>
                                        <p>Сообщений</p>
                                    </div>
                                    <i class="fas fa-envelope fa-2x"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-3">
                        <div class="card text-white bg-warning">
                            <div class="card-body">
                                <div class="d-flex justify-content-between">
                                    <div>
                                        <h4>{{ stats.vip_users }}</h4>
                                        <p>VIP-пользователей</p>
                                    </div>
                                    <i class="fas fa-star fa-2x"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-3">
                        <div class="card text-white bg-info">
                            <div class="card-body">
                                <div class="d-flex justify-content-between">
                                    <div>
                                        <h4>{{ stats.delivery_rate }}%</h4>
                                        <p>Доставлено</p>
                                    </div>
                                    <i class="fas fa-check-circle fa-2x"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                {% if stats.recent_actions %}
                <div class="card">
                    <div class="card-header">
                        <h5>📝 Последние действия</h5>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-sm">
                                <thead>
                                    <tr>
                                        <th>Время</th>
                                        <th>Администратор</th>
                                        <th>Действие</th>
                                        <th>Описание</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for action in stats.recent_actions %}
                                    <tr>
                                        <td>{{ action.created_at[:16] }}</td>
                                        <td>{{ action.admin_name }}</td>
                                        <td>
                                            <span class="badge bg-secondary">{{ action.action_type }}</span>
                                        </td>
                                        <td>{{ action.description }}</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                {% endif %}
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

USERS_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Админ-панель - Пользователи</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/admin/dashboard">
                <i class="fas fa-robot"></i> Админ-панель
            </a>
            <div class="navbar-nav ms-auto">
                <span class="navbar-text me-3">
                    Привет, {{ admin.get_display_name() }}!
                </span>
                <form method="POST" action="/admin/logout" class="d-inline">
                    <button type="submit" class="btn btn-outline-light btn-sm">Выйти</button>
                </form>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row">
            <div class="col-md-3">
                <div class="list-group">
                    <a href="/admin/dashboard" class="list-group-item list-group-item-action">
                        <i class="fas fa-tachometer-alt"></i> Дашборд
                    </a>
                    <a href="/admin/users" class="list-group-item list-group-item-action active">
                        <i class="fas fa-users"></i> Пользователи
                    </a>
                    <a href="/admin/messages" class="list-group-item list-group-item-action">
                        <i class="fas fa-envelope"></i> Сообщения
                    </a>
                    <a href="/admin/logs" class="list-group-item list-group-item-action">
                        <i class="fas fa-history"></i> Логи
                    </a>
                </div>
            </div>
            
            <div class="col-md-9">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h2>👥 Управление пользователями</h2>
                    <form method="GET" class="d-flex">
                        <input type="text" name="search" class="form-control me-2" placeholder="Поиск..." value="{{ search }}">
                        <button type="submit" class="btn btn-outline-primary">
                            <i class="fas fa-search"></i>
                        </button>
                    </form>
                </div>
                
                <div class="card">
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>ID</th>
                                        <th>Имя</th>
                                        <th>Username</th>
                                        <th>Статус</th>
                                        <th>Регистрация</th>
                                        <th>Действия</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for user in users.items %}
                                    <tr>
                                        <td>{{ user.telegram_id }}</td>
                                        <td>{{ user.get_display_name() }}</td>
                                        <td>
                                            {% if user.username %}
                                                @{{ user.username }}
                                            {% else %}
                                                <span class="text-muted">—</span>
                                            {% endif %}
                                        </td>
                                        <td>
                                            {% if user.is_admin %}
                                                <span class="badge bg-danger">Админ</span>
                                            {% elif user.is_vip %}
                                                <span class="badge bg-warning">VIP</span>
                                            {% else %}
                                                <span class="badge bg-secondary">Обычный</span>
                                            {% endif %}
                                        </td>
                                        <td>{{ user.created_at.strftime('%d.%m.%Y') if user.created_at else '—' }}</td>
                                        <td>
                                            {% if not user.is_admin %}
                                                {% if user.is_vip %}
                                                    <button class="btn btn-sm btn-outline-danger" onclick="revokeVip({{ user.id }})">
                                                        Отозвать VIP
                                                    </button>
                                                {% else %}
                                                    <button class="btn btn-sm btn-outline-warning" onclick="grantVip({{ user.id }})">
                                                        Выдать VIP
                                                    </button>
                                                {% endif %}
                                            {% endif %}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        
                        <!-- Пагинация -->
                        {% if users.pages > 1 %}
                        <nav>
                            <ul class="pagination justify-content-center">
                                {% if users.has_prev %}
                                    <li class="page-item">
                                        <a class="page-link" href="?page={{ users.prev_num }}&search={{ search }}">Предыдущая</a>
                                    </li>
                                {% endif %}
                                
                                {% for page_num in users.iter_pages() %}
                                    {% if page_num %}
                                        {% if page_num != users.page %}
                                            <li class="page-item">
                                                <a class="page-link" href="?page={{ page_num }}&search={{ search }}">{{ page_num }}</a>
                                            </li>
                                        {% else %}
                                            <li class="page-item active">
                                                <span class="page-link">{{ page_num }}</span>
                                            </li>
                                        {% endif %}
                                    {% else %}
                                        <li class="page-item disabled">
                                            <span class="page-link">…</span>
                                        </li>
                                    {% endif %}
                                {% endfor %}
                                
                                {% if users.has_next %}
                                    <li class="page-item">
                                        <a class="page-link" href="?page={{ users.next_num }}&search={{ search }}">Следующая</a>
                                    </li>
                                {% endif %}
                            </ul>
                        </nav>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function grantVip(userId) {
            if (confirm('Выдать VIP-статус этому пользователю?')) {
                fetch(`/admin/users/${userId}/grant_vip`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert(data.message);
                        location.reload();
                    } else {
                        alert('Ошибка: ' + data.message);
                    }
                });
            }
        }
        
        function revokeVip(userId) {
            if (confirm('Отозвать VIP-статус у этого пользователя?')) {
                fetch(`/admin/users/${userId}/revoke_vip`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert(data.message);
                        location.reload();
                    } else {
                        alert('Ошибка: ' + data.message);
                    }
                });
            }
        }
    </script>
</body>
</html>
"""

MESSAGES_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Админ-панель - Сообщения</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/admin/dashboard">
                <i class="fas fa-robot"></i> Админ-панель
            </a>
            <div class="navbar-nav ms-auto">
                <span class="navbar-text me-3">
                    Привет, {{ admin.get_display_name() }}!
                </span>
                <form method="POST" action="/admin/logout" class="d-inline">
                    <button type="submit" class="btn btn-outline-light btn-sm">Выйти</button>
                </form>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row">
            <div class="col-md-3">
                <div class="list-group">
                    <a href="/admin/dashboard" class="list-group-item list-group-item-action">
                        <i class="fas fa-tachometer-alt"></i> Дашборд
                    </a>
                    <a href="/admin/users" class="list-group-item list-group-item-action">
                        <i class="fas fa-users"></i> Пользователи
                    </a>
                    <a href="/admin/messages" class="list-group-item list-group-item-action active">
                        <i class="fas fa-envelope"></i> Сообщения
                    </a>
                    <a href="/admin/logs" class="list-group-item list-group-item-action">
                        <i class="fas fa-history"></i> Логи
                    </a>
                </div>
            </div>
            
            <div class="col-md-9">
                <h2>📩 Просмотр сообщений</h2>
                
                <!-- Фильтры -->
                <div class="card mb-3">
                    <div class="card-body">
                        <form method="GET" class="row g-3">
                            <div class="col-md-4">
                                <label class="form-label">Получатель</label>
                                <select name="user_id" class="form-select">
                                    <option value="">Все пользователи</option>
                                    {% for user in users %}
                                    <option value="{{ user.id }}" {% if user.id == selected_user_id %}selected{% endif %}>
                                        {{ user.get_display_name() }}
                                    </option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label">Анонимность</label>
                                <select name="anonymous" class="form-select">
                                    <option value="all" {% if show_anonymous == 'all' %}selected{% endif %}>Все сообщения</option>
                                    <option value="yes" {% if show_anonymous == 'yes' %}selected{% endif %}>Только анонимные</option>
                                    <option value="no" {% if show_anonymous == 'no' %}selected{% endif %}>Только неанонимные</option>
                                </select>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label">&nbsp;</label>
                                <button type="submit" class="btn btn-primary d-block">Применить фильтр</button>
                            </div>
                        </form>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-body">
                        {% if messages and messages.items %}
                        <div class="table-responsive">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>Дата</th>
                                        <th>Получатель</th>
                                        <th>Отправитель</th>
                                        <th>Сообщение</th>
                                        <th>Статус</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for message in messages.items %}
                                    <tr>
                                        <td>{{ message.created_at.strftime('%d.%m.%Y %H:%M') if message.created_at else '—' }}</td>
                                        <td>{{ message.recipient.get_display_name() if message.recipient else '—' }}</td>
                                        <td>
                                            {% if message.is_anonymous %}
                                                <span class="badge bg-secondary">Анонимно</span>
                                            {% else %}
                                                <strong>{{ message.sender_name or 'Неизвестно' }}</strong>
                                                {% if message.sender_contact %}
                                                    <br><small class="text-muted">{{ message.sender_contact }}</small>
                                                {% endif %}
                                            {% endif %}
                                        </td>
                                        <td>
                                            <div style="max-width: 300px; overflow: hidden; text-overflow: ellipsis;">
                                                {{ message.message_text[:100] }}{% if message.message_text|length > 100 %}...{% endif %}
                                            </div>
                                        </td>
                                        <td>
                                            {% if message.is_sent %}
                                                <span class="badge bg-success">Отправлено</span>
                                            {% else %}
                                                <span class="badge bg-warning">В очереди</span>
                                            {% endif %}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        
                        <!-- Пагинация -->
                        {% if messages.pages > 1 %}
                        <nav>
                            <ul class="pagination justify-content-center">
                                {% if messages.has_prev %}
                                    <li class="page-item">
                                        <a class="page-link" href="?page={{ messages.prev_num }}&user_id={{ selected_user_id or '' }}&anonymous={{ show_anonymous }}">Предыдущая</a>
                                    </li>
                                {% endif %}
                                
                                {% for page_num in messages.iter_pages() %}
                                    {% if page_num %}
                                        {% if page_num != messages.page %}
                                            <li class="page-item">
                                                <a class="page-link" href="?page={{ page_num }}&user_id={{ selected_user_id or '' }}&anonymous={{ show_anonymous }}">{{ page_num }}</a>
                                            </li>
                                        {% else %}
                                            <li class="page-item active">
                                                <span class="page-link">{{ page_num }}</span>
                                            </li>
                                        {% endif %}
                                    {% else %}
                                        <li class="page-item disabled">
                                            <span class="page-link">…</span>
                                        </li>
                                    {% endif %}
                                {% endfor %}
                                
                                {% if messages.has_next %}
                                    <li class="page-item">
                                        <a class="page-link" href="?page={{ messages.next_num }}&user_id={{ selected_user_id or '' }}&anonymous={{ show_anonymous }}">Следующая</a>
                                    </li>
                                {% endif %}
                            </ul>
                        </nav>
                        {% endif %}
                        
                        {% else %}
                        <div class="text-center py-4">
                            <i class="fas fa-inbox fa-3x text-muted mb-3"></i>
                            <p class="text-muted">Сообщения не найдены</p>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

LOGS_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Админ-панель - Логи</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/admin/dashboard">
                <i class="fas fa-robot"></i> Админ-панель
            </a>
            <div class="navbar-nav ms-auto">
                <span class="navbar-text me-3">
                    Привет, {{ admin.get_display_name() }}!
                </span>
                <form method="POST" action="/admin/logout" class="d-inline">
                    <button type="submit" class="btn btn-outline-light btn-sm">Выйти</button>
                </form>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row">
            <div class="col-md-3">
                <div class="list-group">
                    <a href="/admin/dashboard" class="list-group-item list-group-item-action">
                        <i class="fas fa-tachometer-alt"></i> Дашборд
                    </a>
                    <a href="/admin/users" class="list-group-item list-group-item-action">
                        <i class="fas fa-users"></i> Пользователи
                    </a>
                    <a href="/admin/messages" class="list-group-item list-group-item-action">
                        <i class="fas fa-envelope"></i> Сообщения
                    </a>
                    <a href="/admin/logs" class="list-group-item list-group-item-action active">
                        <i class="fas fa-history"></i> Логи
                    </a>
                </div>
            </div>
            
            <div class="col-md-9">
                <h2>📝 Логи действий администраторов</h2>
                
                {% if actions %}
                <div class="card">
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>Время</th>
                                        <th>Администратор</th>
                                        <th>Действие</th>
                                        <th>Цель</th>
                                        <th>Описание</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for action in actions.items %}
                                    <tr>
                                        <td>{{ action.created_at.strftime('%d.%m.%Y %H:%M') if action.created_at else '—' }}</td>
                                        <td>{{ action.admin.get_display_name() if action.admin else '—' }}</td>
                                        <td>
                                            <span class="badge bg-info">{{ action.action_type }}</span>
                                        </td>
                                        <td>{{ action.target_user.get_display_name() if action.target_user else '—' }}</td>
                                        <td>{{ action.description }}</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        
                        <!-- Пагинация -->
                        {% if actions.pages > 1 %}
                        <nav>
                            <ul class="pagination justify-content-center">
                                {% if actions.has_prev %}
                                    <li class="page-item">
                                        <a class="page-link" href="?page={{ actions.prev_num }}&action_type={{ selected_action_type }}">Предыдущая</a>
                                    </li>
                                {% endif %}
                                
                                {% for page_num in actions.iter_pages() %}
                                    {% if page_num %}
                                        {% if page_num != actions.page %}
                                            <li class="page-item">
                                                <a class="page-link" href="?page={{ page_num }}&action_type={{ selected_action_type }}">{{ page_num }}</a>
                                            </li>
                                        {% else %}
                                            <li class="page-item active">
                                                <span class="page-link">{{ page_num }}</span>
                                            </li>
                                        {% endif %}
                                    {% else %}
                                        <li class="page-item disabled">
                                            <span class="page-link">…</span>
                                        </li>
                                    {% endif %}
                                {% endfor %}
                                
                                {% if actions.has_next %}
                                    <li class="page-item">
                                        <a class="page-link" href="?page={{ actions.next_num }}&action_type={{ selected_action_type }}">Следующая</a>
                                    </li>
                                {% endif %}
                            </ul>
                        </nav>
                        {% endif %}
                    </div>
                </div>
                {% else %}
                <div class="card">
                    <div class="card-body text-center py-4">
                        <i class="fas fa-history fa-3x text-muted mb-3"></i>
                        <p class="text-muted">Логи недоступны или пусты</p>
                        <small class="text-muted">Возможно, система логирования еще не настроена</small>
                    </div>
                </div>
                {% endif %}
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

