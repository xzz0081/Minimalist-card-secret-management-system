from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, g
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
import logging
import threading
from sqlalchemy import func
import pytz

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cards.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['DEBUG'] = True  # 启用调试模式

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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

class RateLimit:
    """请求频率限制实现"""
    def __init__(self):
        self.requests = {}
        self.last_cleanup = time.time()
        self._lock = threading.Lock()  # 添加线程锁

    def is_allowed(self, ip):
        """检查IP是否允许请求"""
        with self._lock:  # 使用线程锁保护并发访问
            now = time.time()
            
            # 清理过期的请求记录
            if now - self.last_cleanup > 60:
                self._cleanup(now)
            
            # 获取IP的请求记录
            if ip not in self.requests:
                self.requests[ip] = []
            
            # 获取配置的限制
            window = settings.get('rate_limit_window', 60)
            max_requests = settings.get('rate_limit_requests', 60)
            
            # 清理当前IP的过期请求
            self.requests[ip] = [t for t in self.requests[ip] if now - t < window]
            
            # 检查是否超过限制
            if len(self.requests[ip]) >= max_requests:
                return False
            
            # 添加新请求
            self.requests[ip].append(now)
            return True

    def _cleanup(self, now):
        """清理过期的请求记录"""
        window = settings.get('rate_limit_window', 60)
        for ip in list(self.requests.keys()):
            self.requests[ip] = [t for t in self.requests[ip] if now - t < window]
            if not self.requests[ip]:
                del self.requests[ip]
        self.last_cleanup = now

rate_limiter = RateLimit()

def rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 检查API是否启用
        if not settings.get('api_enabled', True):
            return jsonify({
                'valid': False,
                'message': 'API接口已关闭'
            }), 403
            
        if not rate_limiter.is_allowed(request.remote_addr):
            return jsonify({
                'valid': False,
                'message': f'请求过于频繁，请在{settings.get("rate_limit_window", 60)}秒后再试'
            }), 429
        return f(*args, **kwargs)
    return decorated_function

def get_local_time():
    """获取本地时间"""
    return datetime.now()

class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    card_key = db.Column(db.String(32), unique=True, nullable=False)
    remark = db.Column(db.String(255), nullable=True, default="")
    minutes = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=get_local_time)
    is_used = db.Column(db.Boolean, default=False)
    used_at = db.Column(db.DateTime, nullable=True)
    device_id = db.Column(db.String(500), nullable=True)  # 存储多个设备ID，用逗号分隔
    max_devices = db.Column(db.Integer, default=1)  # 最大允许设备数量

    @classmethod
    def generate_bulk_cards(cls, minutes, count, max_devices=1):
        """批量生成卡密"""
        cards = []
        for _ in range(count):
            card_key = secrets.token_hex(16)
            cards.append(cls(card_key=card_key, minutes=minutes, max_devices=max_devices))
        return cards

    def add_device(self, device_id):
        """添加设备ID"""
        device_list = self.get_devices()
        if device_id not in device_list:
            if len(device_list) >= self.max_devices:
                return False, "超出最大设备数量限制"
            device_list.append(device_id)
            self.device_id = ','.join(device_list)
        return True, "设备添加成功"

    def get_devices(self):
        """获取设备ID列表"""
        return self.device_id.split(',') if self.device_id else []

    def is_device_allowed(self, device_id):
        """检查设备是否允许使用"""
        device_list = self.get_devices()
        return device_id in device_list or len(device_list) < self.max_devices

    @classmethod
    def export_to_csv(cls, cards):
        """导出卡密到CSV格式"""
        csv_data = []
        headers = ['卡密', '备注', '时长(分钟)', '创建时间', '状态', '首次使用时间', '剩余时间', '最大设备数', '已用设备数']
        csv_data.append(headers)
        
        for card in cards:
            remaining_minutes = card._calculate_remaining_minutes()
            status = card.get_status()
            device_count = len(card.get_devices()) if card.device_id else 0
            row = [
                card.card_key,
                card.remark if card.remark else '',
                str(card.minutes),
                card.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                status,
                card.used_at.strftime('%Y-%m-%d %H:%M:%S') if card.used_at else '',
                str(remaining_minutes),
                str(card.max_devices),
                str(device_count)
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

    def _calculate_remaining_minutes(self):
        """计算卡密剩余分钟数"""
        if not self.is_used:
            # 未使用的卡密，返回完整时长
            return self.minutes
            
        if not self.used_at:
            # 异常情况：已使用但没有使用时间
            return 0
            
        # 计算从首次使用开始的剩余时间
        current_time = get_local_time()
        expiration_time = self.used_at + timedelta(minutes=self.minutes)
        
        if current_time >= expiration_time:
            return 0
            
        # 计算剩余时间（精确到秒）
        remaining_seconds = (expiration_time - current_time).total_seconds()
        return max(0, int(remaining_seconds / 60))

    def get_remaining_time(self):
        """获取剩余时间的详细信息"""
        if not self.is_used:
            return {
                'hours': 0,
                'minutes': self.minutes,
                'seconds': 0,
                'total_seconds': self.minutes * 60
            }
            
        if not self.used_at or self.is_expired():
            return {
                'hours': 0,
                'minutes': 0,
                'seconds': 0,
                'total_seconds': 0
            }
        
        current_time = get_local_time()
        expiration_time = self.used_at + timedelta(minutes=self.minutes)
        remaining_seconds = int((expiration_time - current_time).total_seconds())
        
        hours = remaining_seconds // 3600
        minutes = (remaining_seconds % 3600) // 60
        seconds = remaining_seconds % 60
        
        return {
            'hours': hours,
            'minutes': minutes,
            'seconds': seconds,
            'total_seconds': remaining_seconds
        }

    def to_dict(self):
        """将卡密对象转换为字典，用于 JSON 序列化"""
        return {
            'id': self.id,
            'card_key': self.card_key,
            'remark': self.remark if self.remark else '',
            'minutes': self.minutes,
            'is_used': self.is_used,
            'used_at': self.used_at.isoformat() if self.used_at else None,
            'created_at': self.created_at.isoformat(),
            'max_devices': self.max_devices,
            'device_count': len(self.get_devices()),
            'status': self.get_status(),
            'remaining_minutes': self._calculate_remaining_minutes() if self.is_used else self.minutes
        }

    def is_expired(self):
        """判断卡密是否过期"""
        if not self.is_used:
            # 未使用的卡密永不过期
            return False
            
        if not self.used_at:
            # 异常情况：已使用但没有使用时间
            return True
            
        # 检查是否超过有效期
        current_time = get_local_time()
        expiration_time = self.used_at + timedelta(minutes=self.minutes)
        return current_time >= expiration_time

    def get_status(self):
        """获取卡密状态"""
        if not self.is_used:
            return "未使用"
        elif self.is_expired():
            return "已过期"
        else:
            return "使用中"

def broadcast_card_update():
    """广播卡密更新"""
    try:
        cards = Card.query.all()
        card_list = [card.to_dict() for card in cards]
        socketio.emit('cards_update', {'cards': card_list})
    except Exception as e:
        app.logger.error(f"广播卡密更新出错: {str(e)}")

class Settings:
    def __init__(self):
        self.config_file = 'config.json'
        self.default_settings = {
            'per_page': 10,
            'rate_limit_requests': 60,
            'rate_limit_window': 60,
            'site_name': '卡密管理系统',
            'api_enabled': True
        }
        self.load()

    def load(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
            else:
                self.settings = self.default_settings
                self.save()
        except Exception as e:
            app.logger.error(f"加载配置出错: {str(e)}")
            self.settings = self.default_settings

    def save(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            app.logger.error(f"保存配置出错: {str(e)}")

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save()

settings = Settings()

class AccessLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    access_time = db.Column(db.DateTime, nullable=False, default=datetime.now)
    ip_address = db.Column(db.String(50), nullable=False)
    device_id = db.Column(db.String(32), nullable=False)
    path = db.Column(db.String(200), nullable=False)
    method = db.Column(db.String(10), nullable=False)
    status_code = db.Column(db.Integer, nullable=False)
    user_agent = db.Column(db.String(200))
    card_key = db.Column(db.String(32))  # 如果涉及卡密操作，记录相关卡密

    def to_dict(self):
        return {
            'id': self.id,
            'access_time': self.access_time.strftime('%Y-%m-%d %H:%M:%S'),
            'ip_address': self.ip_address,
            'device_id': self.device_id,
            'path': self.path,
            'method': self.method,
            'status_code': self.status_code,
            'user_agent': self.user_agent,
            'card_key': self.card_key
        }

@app.before_request
def log_request():
    try:
        # 定义允许记录日志的路径和对应的操作类型
        card_operations = {
            '/api/verify_card': '验证卡密',
            '/add_card': '添加卡密',
            '/delete_card': '删除卡密',
            '/import_cards': '导入卡密',
            '/export_cards': '导出卡密'
        }
        
        # 只记录定义的卡密操作
        if request.path in card_operations:
            device_id = generate_device_id(request)
            # 获取请求中的卡密信息
            card_key = None
            if request.is_json and request.get_json() and 'card_key' in request.get_json():
                card_key = request.get_json().get('card_key')
            elif request.form and 'card_key' in request.form:
                card_key = request.form.get('card_key')
            elif '/delete_card/' in request.path:
                # 对于删除操作，从路径中提取卡密ID并查找对应的卡密
                try:
                    card_id = int(request.path.split('/')[-1])
                    card = Card.query.get(card_id)
                    if card:
                        card_key = card.card_key
                except (ValueError, AttributeError):
                    pass
            
            log = AccessLog(
                ip_address=request.remote_addr,
                device_id=device_id,
                path=request.path,
                method=request.method,
                status_code=200,  # 将在after_request中更新
                user_agent=str(request.user_agent),
                card_key=card_key
            )
            db.session.add(log)
            db.session.commit()
            # 存储日志ID用于后续更新状态码
            g.log_id = log.id
    except Exception as e:
        error_logger.error(f"记录访问日志出错: {str(e)}", exc_info=True)

@app.after_request
def update_log_status(response):
    try:
        if hasattr(g, 'log_id'):
            log = AccessLog.query.get(g.log_id)
            if log:
                log.status_code = response.status_code
                db.session.commit()
    except Exception as e:
        error_logger.error(f"更新日志状态出错: {str(e)}", exc_info=True)
    return response

@app.route('/')
def index():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = settings.get('per_page', 10)
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        
        # 获取各状态的卡密数量
        current_time = get_local_time()
        unused_count = Card.query.filter_by(is_used=False).count()
        
        # 使用中的卡密数量
        used_cards = Card.query.filter(
            Card.is_used == True,
            Card.used_at != None
        ).all()
        used_count = sum(
            1 for card in used_cards
            if card.used_at + timedelta(minutes=card.minutes) > current_time
        )
        
        # 已过期的卡密数量
        expired_count = sum(
            1 for card in used_cards
            if card.used_at + timedelta(minutes=card.minutes) <= current_time
        )
        
        # 构建查询
        query = Card.query
        
        # 应用过滤条件
        if status:
            if status == 'unused':
                query = query.filter_by(is_used=False)
            elif status == 'used':
                # 使用中的卡密：已使用且未过期
                query = query.filter(
                    Card.is_used == True,
                    Card.used_at != None
                )
                # 在Python中过滤未过期的卡密
                cards = query.all()
                valid_card_ids = [
                    card.id for card in cards
                    if card.used_at + timedelta(minutes=card.minutes) > current_time
                ]
                query = Card.query.filter(Card.id.in_(valid_card_ids))
            elif status == 'expired':
                # 已过期的卡密：已使用且已过期
                query = query.filter(
                    Card.is_used == True,
                    Card.used_at != None
                )
                # 在Python中过滤已过期的卡密
                cards = query.all()
                expired_card_ids = [
                    card.id for card in cards
                    if card.used_at + timedelta(minutes=card.minutes) <= current_time
                ]
                query = Card.query.filter(Card.id.in_(expired_card_ids))
        
        # 应用搜索条件
        if search:
            query = query.filter(Card.card_key.like(f'%{search}%'))
        
        # 应用排序
        query = query.order_by(Card.created_at.desc())
        
        # 执行分页
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        cards = pagination.items if pagination else []
        
        return render_template('index.html', 
                             cards=cards, 
                             pagination=pagination,
                             status=status,
                             search=search,
                             unused_count=unused_count,
                             used_count=used_count,
                             expired_count=expired_count,
                             settings=settings.settings)
    except Exception as e:
        logger.error(f"访问首页出错: {str(e)}", exc_info=True)
        return render_template('index.html', 
                             cards=[], 
                             pagination=None,
                             status=status,
                             search=search,
                             unused_count=0,
                             used_count=0,
                             expired_count=0,
                             error="获取卡密列表失败",
                             settings=settings.settings)

@app.route('/add_card', methods=['POST'])
def add_card():
    try:
        minutes = request.form.get('minutes', type=int)
        max_devices = request.form.get('max_devices', type=int, default=1)
        
        if not minutes or minutes <= 0:
            return jsonify({'error': '无效的分钟数'}), 400
        if max_devices <= 0:
            return jsonify({'error': '无效的设备数量限制'}), 400
        
        card_key = secrets.token_hex(16)
        card = Card(card_key=card_key, minutes=minutes, max_devices=max_devices)
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
        
        # 检查设备是否允许使用
        if card.is_used and not card.is_device_allowed(current_device_id):
            return jsonify({
                'valid': False,
                'message': f'超出最大设备数量限制（{card.max_devices}台设备）'
            }), 403
        
        # 如果卡密已过期，直接返回
        if card.is_expired():
            return jsonify({
                'valid': False,
                'remaining_minutes': 0,
                'message': '卡密已过期'
            })
        
        # 如果是首次使用卡密
        if not card.is_used:
            card.is_used = True
            card.used_at = get_local_time()
            success, message = card.add_device(current_device_id)
            if not success:
                return jsonify({
                    'valid': False,
                    'message': message
                }), 403
            
            db.session.commit()
            # 立即广播更新
            try:
                cards = Card.query.all()
                card_list = [card.to_dict() for card in cards]
                socketio.emit('cards_update', {'cards': card_list})
            except Exception as e:
                app.logger.error(f"广播卡密更新出错: {str(e)}")
            
            return jsonify({
                'valid': True,
                'remaining_minutes': card.minutes,
                'message': '卡密首次使用成功'
            })
        
        # 如果是新设备，添加到设备列表
        if current_device_id not in card.get_devices():
            success, message = card.add_device(current_device_id)
            if not success:
                return jsonify({
                    'valid': False,
                    'message': message
                }), 403
            db.session.commit()
            # 立即广播更新
            try:
                cards = Card.query.all()
                card_list = [card.to_dict() for card in cards]
                socketio.emit('cards_update', {'cards': card_list})
            except Exception as e:
                app.logger.error(f"广播卡密更新出错: {str(e)}")
        
        # 返回剩余时间
        remaining_minutes = card._calculate_remaining_minutes()
        return jsonify({
            'valid': True,
            'remaining_minutes': remaining_minutes,
            'message': '卡密有效'
        })
        
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
        max_devices = request.form.get('max_devices', type=int, default=1)
        
        if not minutes or minutes <= 0 or not count or count <= 0:
            return jsonify({'error': '无效的参数'}), 400
        if max_devices <= 0:
            return jsonify({'error': '无效的设备数量限制'}), 400
        
        cards = Card.generate_bulk_cards(minutes, count, max_devices)
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

@app.route('/settings')
def settings_page():
    return render_template('settings.html', settings=settings.settings)

@app.route('/settings/update', methods=['POST'])
def update_settings():
    """更新系统设置"""
    try:
        # 获取表单数据
        site_name = request.form.get('site_name')
        per_page = request.form.get('per_page', type=int)
        rate_limit_requests = request.form.get('rate_limit_requests', type=int)
        rate_limit_window = request.form.get('rate_limit_window', type=int)
        api_enabled = request.form.get('api_enabled') == 'on'

        # 验证数据
        if not site_name or per_page <= 0 or rate_limit_requests <= 0 or rate_limit_window <= 0:
            return jsonify({'error': '无效的设置参数'}), 400

        # 更新设置
        settings.settings.update({
            'site_name': site_name,
            'per_page': per_page,
            'rate_limit_requests': rate_limit_requests,
            'rate_limit_window': rate_limit_window,
            'api_enabled': api_enabled
        })
        settings.save()

        return jsonify({'message': '设置已更新'})
    except Exception as e:
        app.logger.error(f"更新设置出错: {str(e)}")
        return jsonify({'error': '更新设置失败'}), 500

@app.route('/logs')
def view_logs():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = settings.get('per_page', 10)
        
        # 获取卡密筛选参数
        card_key_filter = request.args.get('card_key', '').strip()
        
        query = AccessLog.query
        
        # 应用卡密筛选条件
        if card_key_filter:
            query = query.filter(AccessLog.card_key.like(f'%{card_key_filter}%'))
        
        # 按时间倒序排序
        query = query.order_by(AccessLog.access_time.desc())
        
        # 执行分页
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return render_template('logs.html',
                             logs=pagination.items,
                             pagination=pagination,
                             card_key_filter=card_key_filter,
                             settings=settings.settings)
    except Exception as e:
        error_logger.error(f"访问日志页面出错: {str(e)}", exc_info=True)
        return render_template('logs.html',
                             logs=[],
                             error="获取日志列表失败",
                             settings=settings.settings)

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html', settings=settings.settings), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html', settings=settings.settings), 500

@socketio.on('connect')
def handle_connect():
    """处理客户端连接"""
    app.logger.info('Client connected')
    # 发送当前卡密状态
    broadcast_card_update()

@socketio.on('disconnect')
def handle_disconnect():
    """处理客户端断开连接"""
    app.logger.info('Client disconnected')

@socketio.on('request_update')
def handle_update_request():
    """处理客户端请求更新数据"""
    broadcast_card_update()

@socketio.on('status_check')
def handle_status_check(data):
    """处理状态检查请求"""
    try:
        # 获取所有卡密并检查状态
        cards = Card.query.all()
        status_changed = False
        
        for card in cards:
            if card.is_used and not card.is_expired() and card._calculate_remaining_minutes() <= 0:
                status_changed = True
                
        if status_changed:
            # 如果有状态变化，广播更新
            broadcast_card_update()
    except Exception as e:
        app.logger.error(f"状态检查出错: {str(e)}")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, host='0.0.0.0', port=8888, debug=False)