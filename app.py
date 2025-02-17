from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from datetime import datetime, timedelta
import secrets
import os
from functools import wraps
import time
import hashlib
import json
import csv
from io import StringIO

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cards.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 添加请求频率限制配置
app.config['RATELIMIT_STORAGE_URL'] = 'memory://'
app.config['RATELIMIT_STRATEGY'] = 'fixed-window'
app.config['RATELIMIT_DEFAULT'] = "60/minute"

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

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
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    is_used = db.Column(db.Boolean, default=False)
    used_at = db.Column(db.DateTime, nullable=True)
    device_id = db.Column(db.String(32), nullable=True)

    @classmethod
    def generate_bulk_cards(cls, minutes, count):
        """批量生成卡密"""
        cards = []
        for _ in range(count):
            card_key = secrets.token_hex(16)
            cards.append(cls(card_key=card_key, minutes=minutes))
        return cards

    @classmethod
    def export_to_csv(cls, cards):
        """导出卡密到CSV格式"""
        csv_data = []
        headers = ['卡密', '时长(分钟)', '创建时间', '状态', '使用时间', '剩余时间']
        csv_data.append(headers)
        
        for card in cards:
            status = '未使用' if not card.is_used else '使用中' if card._calculate_remaining_minutes() > 0 else '已过期'
            row = [
                card.card_key,
                str(card.minutes),
                card.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                status,
                card.used_at.strftime('%Y-%m-%d %H:%M:%S') if card.used_at else '',
                str(card._calculate_remaining_minutes())
            ]
            csv_data.append(row)
        return csv_data

    @classmethod
    def import_from_csv(cls, csv_data):
        """从CSV导入卡密"""
        imported_cards = []
        for row in csv_data[1:]:  # Skip header row
            if len(row) >= 2:  # At least card_key and minutes are required
                card_key, minutes = row[0], int(row[1])
                if not cls.query.filter_by(card_key=card_key).first():
                    card = cls(card_key=card_key, minutes=minutes)
                    imported_cards.append(card)
        return imported_cards

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
        if datetime.now() >= expiration_time:
            return 0
        return int((expiration_time - datetime.now()).total_seconds() / 60)

def broadcast_card_update():
    """广播卡密更新"""
    try:
        cards = Card.query.all()
        card_list = [card.to_dict() for card in cards]
        socketio.emit('cards_update', {'cards': card_list})
    except Exception as e:
        app.logger.error(f"广播卡密更新出错: {str(e)}")

@app.route('/')
def index():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        
        # 构建查询
        query = Card.query
        
        # 应用过滤条件
        if status:
            if status == 'unused':
                query = query.filter_by(is_used=False)
            elif status == 'used':
                query = query.filter_by(is_used=True)
            elif status == 'expired':
                query = query.filter(
                    Card.is_used == True,
                    Card.used_at <= datetime.now() - timedelta(minutes=Card.minutes)
                )
        
        # 应用搜索条件
        if search:
            query = query.filter(Card.card_key.like(f'%{search}%'))
        
        # 应用排序
        query = query.order_by(Card.created_at.desc())
        
        # 执行分页
        pagination = query.paginate(page=page, per_page=per_page)
        cards = pagination.items
        
        return render_template('index.html', 
                             cards=cards, 
                             pagination=pagination,
                             status=status,
                             search=search)
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
        
        # 广播更新
        broadcast_card_update()
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
        
        # 广播更新
        broadcast_card_update()
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"删除卡密出错: {str(e)}")
        db.session.rollback()
        return jsonify({'error': '删除卡密失败'}), 500

@app.route('/api/verify_card', methods=['POST'])
@rate_limit
def verify_card():
    try:
        data = request.get_json()
        if not data or 'card_key' not in data:
            return jsonify({
                'valid': False,
                'message': '缺少卡密参数'
            }), 400
            
        card_key = data['card_key']
        current_device_id = generate_device_id(request)
        card = Card.query.filter_by(card_key=card_key).first()
        
        if not card:
            return jsonify({
                'valid': False,
                'message': '卡密不存在'
            }), 404
        
        response_data = None
        if card.is_used:
            # 检查设备是否匹配
            if card.device_id and card.device_id != current_device_id:
                response_data = {
                    'valid': False,
                    'message': '该卡密已被其他设备使用'
                }
                return jsonify(response_data), 403
                
            remaining_minutes = 0
            if card.used_at:
                expiration_time = card.used_at + timedelta(minutes=card.minutes)
                if datetime.now() < expiration_time:
                    remaining_minutes = int((expiration_time - datetime.now()).total_seconds() / 60)
                response_data = {
                    'valid': remaining_minutes > 0,
                    'remaining_minutes': remaining_minutes,
                    'message': '卡密有效' if remaining_minutes > 0 else '卡密已过期'
                }
            else:
                response_data = {
                    'valid': False,
                    'message': '卡密已过期'
                }
        else:
            # 首次使用卡密
            card.is_used = True
            card.used_at = datetime.now()
            card.device_id = current_device_id
            db.session.commit()
            
            response_data = {
                'valid': True,
                'remaining_minutes': card.minutes,
                'message': '卡密首次使用成功'
            }
        
        # 广播更新
        broadcast_card_update()
        return jsonify(response_data)
    except Exception as e:
        app.logger.error(f"验证卡密出错: {str(e)}")
        db.session.rollback()
        return jsonify({
            'valid': False,
            'message': '服务器内部错误'
        }), 500

@app.route('/add_bulk_cards', methods=['POST'])
def add_bulk_cards():
    try:
        minutes = request.form.get('minutes', type=int)
        count = request.form.get('count', type=int)
        
        if not minutes or minutes <= 0 or not count or count <= 0:
            return jsonify({'error': '无效的参数'}), 400
        
        cards = Card.generate_bulk_cards(minutes, count)
        db.session.bulk_save_objects(cards)
        db.session.commit()
        
        # 广播更新
        broadcast_card_update()
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"批量添加卡密出错: {str(e)}")
        db.session.rollback()
        return jsonify({'error': '批量添加卡密失败'}), 500

@app.route('/export_cards')
def export_cards():
    try:
        # 获取所有卡密
        cards = Card.query.all()
        
        # 生成CSV数据
        csv_data = Card.export_to_csv(cards)
        
        # 创建CSV字符串
        si = StringIO()
        writer = csv.writer(si)
        writer.writerows(csv_data)
        
        # 创建响应
        output = si.getvalue()
        si.close()
        
        return send_file(
            StringIO(output),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'cards_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    except Exception as e:
        app.logger.error(f"导出卡密出错: {str(e)}")
        return jsonify({'error': '导出卡密失败'}), 500

@app.route('/import_cards', methods=['POST'])
def import_cards():
    try:
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
            
        if not file.filename.endswith('.csv'):
            return jsonify({'error': '只支持CSV文件'}), 400
        
        # 读取CSV文件
        stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_data = list(csv.reader(stream))
        
        # 导入卡密
        cards = Card.import_from_csv(csv_data)
        if not cards:
            return jsonify({'error': '没有有效的卡密数据可导入'}), 400
            
        db.session.bulk_save_objects(cards)
        db.session.commit()
        
        # 广播更新
        broadcast_card_update()
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"导入卡密出错: {str(e)}")
        db.session.rollback()
        return jsonify({'error': '导入卡密失败'}), 500

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
    socketio.run(app, host='0.0.0.0', port=8888, debug=False)