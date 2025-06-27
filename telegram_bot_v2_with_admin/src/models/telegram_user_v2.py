from flask_sqlalchemy import SQLAlchemy
import uuid
import string
import random
import hashlib
from datetime import datetime, timedelta

db = SQLAlchemy()

class TelegramUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False)
    username = db.Column(db.String(80), nullable=True)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    unique_link_id = db.Column(db.String(32), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Новые поля для админ-панели и VIP
    is_vip = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    vip_granted_at = db.Column(db.DateTime, nullable=True)
    vip_granted_by = db.Column(db.Integer, db.ForeignKey('telegram_user.id'), nullable=True)
    
    # Связи
    messages = db.relationship('AnonymousMessage', backref='recipient', lazy=True, foreign_keys='AnonymousMessage.recipient_id')
    vip_settings = db.relationship('VIPMessageSettings', backref='user', uselist=False, lazy=True)
    admin_sessions = db.relationship('AdminSession', backref='admin', lazy=True)
    admin_actions = db.relationship('AdminAction', backref='admin', lazy=True, foreign_keys='AdminAction.admin_id')
    granted_vips = db.relationship('TelegramUser', backref='vip_granter', remote_side=[id], lazy=True)

    def __init__(self, telegram_id, username=None, first_name=None, last_name=None):
        self.telegram_id = telegram_id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.unique_link_id = self.generate_unique_link_id()

    @staticmethod
    def generate_unique_link_id():
        """Генерирует уникальный идентификатор для ссылки пользователя"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=32))

    def get_anonymous_link(self, base_url):
        """Возвращает полную ссылку для отправки анонимных сообщений"""
        return f"{base_url}/send/{self.unique_link_id}"

    def grant_vip(self, admin_user):
        """Выдает VIP-статус пользователю"""
        if not admin_user.is_admin:
            raise ValueError("Только администраторы могут выдавать VIP-статус")
        
        self.is_vip = True
        self.vip_granted_at = datetime.utcnow()
        self.vip_granted_by = admin_user.id
        
        # Создаем настройки VIP по умолчанию
        if not self.vip_settings:
            vip_settings = VIPMessageSettings(user_id=self.id)
            db.session.add(vip_settings)
        
        # Логируем действие
        action = AdminAction(
            admin_id=admin_user.id,
            action_type='grant_vip',
            target_user_id=self.id,
            description=f'VIP-статус выдан пользователю {self.first_name} (@{self.username})'
        )
        db.session.add(action)

    def revoke_vip(self, admin_user):
        """Отзывает VIP-статус у пользователя"""
        if not admin_user.is_admin:
            raise ValueError("Только администраторы могут отзывать VIP-статус")
        
        self.is_vip = False
        self.vip_granted_at = None
        self.vip_granted_by = None
        
        # Логируем действие
        action = AdminAction(
            admin_id=admin_user.id,
            action_type='revoke_vip',
            target_user_id=self.id,
            description=f'VIP-статус отозван у пользователя {self.first_name} (@{self.username})'
        )
        db.session.add(action)

    def get_display_name(self):
        """Возвращает отображаемое имя пользователя"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.username:
            return f"@{self.username}"
        else:
            return f"User {self.telegram_id}"

    def __repr__(self):
        return f'<TelegramUser {self.telegram_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'telegram_id': self.telegram_id,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'unique_link_id': self.unique_link_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_vip': self.is_vip,
            'is_admin': self.is_admin,
            'vip_granted_at': self.vip_granted_at.isoformat() if self.vip_granted_at else None,
            'display_name': self.get_display_name()
        }


class AnonymousMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('telegram_user.id'), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    sender_ip = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    is_sent = db.Column(db.Boolean, default=False)
    
    # Новые поля для VIP-функций
    sender_name = db.Column(db.String(100), nullable=True)
    sender_contact = db.Column(db.String(200), nullable=True)
    is_anonymous = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f'<AnonymousMessage {self.id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'recipient_id': self.recipient_id,
            'message_text': self.message_text,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_sent': self.is_sent,
            'sender_name': self.sender_name,
            'sender_contact': self.sender_contact,
            'is_anonymous': self.is_anonymous,
            'recipient_name': self.recipient.get_display_name() if self.recipient else None
        }

    def get_formatted_message(self):
        """Возвращает отформатированное сообщение для отправки в Telegram"""
        if self.is_anonymous:
            return f"📩 Анонимное сообщение:\n\n{self.message_text}"
        else:
            header = "📩 Сообщение"
            if self.sender_name:
                header += f" от {self.sender_name}"
            if self.sender_contact:
                header += f" ({self.sender_contact})"
            header += ":\n\n"
            return header + self.message_text


class AdminSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('telegram_user.id'), nullable=False)
    session_token = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def __init__(self, admin_id, duration_hours=24):
        self.admin_id = admin_id
        self.session_token = self.generate_session_token()
        self.expires_at = datetime.utcnow() + timedelta(hours=duration_hours)

    @staticmethod
    def generate_session_token():
        """Генерирует безопасный токен сессии"""
        random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        return hashlib.sha256(random_string.encode()).hexdigest()

    def is_valid(self):
        """Проверяет, действительна ли сессия"""
        return self.is_active and datetime.utcnow() < self.expires_at

    def invalidate(self):
        """Деактивирует сессию"""
        self.is_active = False

    def __repr__(self):
        return f'<AdminSession {self.id}>'


class AdminAction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('telegram_user.id'), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    target_user_id = db.Column(db.Integer, db.ForeignKey('telegram_user.id'), nullable=True)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Связи
    target_user = db.relationship('TelegramUser', foreign_keys=[target_user_id], lazy=True)

    def __repr__(self):
        return f'<AdminAction {self.id}: {self.action_type}>'

    def to_dict(self):
        return {
            'id': self.id,
            'admin_id': self.admin_id,
            'admin_name': self.admin.get_display_name() if self.admin else None,
            'action_type': self.action_type,
            'target_user_id': self.target_user_id,
            'target_user_name': self.target_user.get_display_name() if self.target_user else None,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class VIPMessageSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('telegram_user.id'), nullable=False, unique=True)
    allow_non_anonymous = db.Column(db.Boolean, default=True, nullable=False)
    require_contact = db.Column(db.Boolean, default=False, nullable=False)
    custom_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    def __repr__(self):
        return f'<VIPMessageSettings {self.user_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'allow_non_anonymous': self.allow_non_anonymous,
            'require_contact': self.require_contact,
            'custom_message': self.custom_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

