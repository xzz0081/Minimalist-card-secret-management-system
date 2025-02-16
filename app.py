from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import secrets
import os
from functools import wraps
import time
import hashlib

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cards.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 添加请求频率限制配置
app.config['RATELIMIT_STORAGE_URL'] = 'memory://'
app.config['RATELIMIT_STRATEGY'] = 'fixed-window'
app.config['RATELIMIT_DEFAULT'] = "60/minute"

db = SQLAlchemy(app)

def generate_device_id(request):
    """根据请求信息生成设备ID"""
    # 使用用户代理、IP地址和其他信息生成唯一设备标识
    device_info = f"{request.user_agent.string}|{request.remote_addr}"
    return hashlib.md5(device_info.encode()).hexdigest()

# 简单的内存请求限制实现
class RateLimit:
    def __init__(self, requests=60, window=60):
        self.requests = requests
        self.window = window
        self.tokens = {}
    
    def is_allowed(self, key):
        now = time.time()
        self.cleanup(now)
        
        if key not in self.tokens:
            self.tokens[key] = []
        
        self.tokens[key].append(now)
        
        return len(self.tokens[key]) <= self.requests
    
    def cleanup(self, now):
        min_time = now - self.window
        for key in list(self.tokens.keys()):
            self.tokens[key] = [t for t in self.tokens[key] if t > min_time]
            if not self.tokens[key]:
                del self.tokens[key]

rate_limiter = RateLimit()

def rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not rate_limiter.is_allowed(request.remote_addr):
            return jsonify({
                'valid': False,
                'message': '请求过于频繁，请稍后再试'
            }), 429
        return f(*args, **kwargs)
    return decorated_function

class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    card_key = db.Column(db.String(32), unique=True, nullable=False)
    minutes = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_used = db.Column(db.Boolean, default=False)
    used_at = db.Column(db.DateTime, nullable=True)
    device_id = db.Column(db.String(32), nullable=True)  # 新增：设备标识字段

    def to_dict(self):
        return {
            'id': self.id,
            'card_key': self.card_key,
            'minutes': self.minutes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_used': self.is_used,
            'used_at': self.used_at.isoformat() if self.used_at else None,
            'device_id': self.device_id,
            'remaining_minutes': self._calculate_remaining_minutes()
        }
    
    def _calculate_remaining_minutes(self):
        if not self.is_used or not self.used_at:
            return self.minutes
        expiration_time = self.used_at + timedelta(minutes=self.minutes)
        if datetime.utcnow() >= expiration_time:
            return 0
        return int((expiration_time - datetime.utcnow()).total_seconds() / 60)

@app.route('/')
def index():
    try:
        cards = Card.query.all()
        return render_template('index.html', cards=cards)
    except Exception as e:
        app.logger.error(f"访问首页出错: {str(e)}")
        return render_template('index.html', cards=[], error="获取卡密列表失败")

@app.route('/add_card', methods=['POST'])
def add_card():
    try:
        minutes = request.form.get('minutes', type=int)
        if not minutes or minutes <= 0:
            return jsonify({'error': '无效的分钟数'}), 400
        
        card_key = secrets.token_hex(16)
        card = Card(card_key=card_key, minutes=minutes)
        db.session.add(card)
        db.session.commit()
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"添加卡密出错: {str(e)}")
        db.session.rollback()
        return jsonify({'error': '添加卡密失败'}), 500

@app.route('/delete_card/<int:card_id>', methods=['POST'])
def delete_card(card_id):
    try:
        card = Card.query.get_or_404(card_id)
        db.session.delete(card)
        db.session.commit()
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"删除卡密出错: {str(e)}")
        db.session.rollback()
        return jsonify({'error': '删除卡密失败'}), 500

@app.route('/api/verify_card/<card_key>')
@rate_limit
def verify_card(card_key):
    try:
        current_device_id = generate_device_id(request)
        card = Card.query.filter_by(card_key=card_key).first()
        
        if not card:
            return jsonify({
                'valid': False,
                'message': '卡密不存在'
            }), 404
        
        if card.is_used:
            # 检查设备是否匹配
            if card.device_id and card.device_id != current_device_id:
                return jsonify({
                    'valid': False,
                    'message': '该卡密已被其他设备使用'
                }), 403
                
            remaining_minutes = 0
            if card.used_at:
                expiration_time = card.used_at + timedelta(minutes=card.minutes)
                if datetime.utcnow() < expiration_time:
                    remaining_minutes = int((expiration_time - datetime.utcnow()).total_seconds() / 60)
                return jsonify({
                    'valid': remaining_minutes > 0,
                    'remaining_minutes': remaining_minutes,
                    'message': '卡密有效' if remaining_minutes > 0 else '卡密已过期'
                })
            return jsonify({
                'valid': False,
                'message': '卡密已过期'
            })
        
        # 首次使用卡密
        card.is_used = True
        card.used_at = datetime.utcnow()
        card.device_id = current_device_id  # 记录设备标识
        db.session.commit()
        
        return jsonify({
            'valid': True,
            'remaining_minutes': card.minutes,
            'message': '卡密首次使用成功'
        })
    except Exception as e:
        app.logger.error(f"验证卡密出错: {str(e)}")
        db.session.rollback()
        return jsonify({
            'valid': False,
            'message': '服务器内部错误'
        }), 500

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': '请求的资源不存在'}), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': '服务器内部错误'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 