# 卡密管理系统

这是一个简单的卡密管理系统，提供Web界面进行卡密管理，并提供API接口进行卡密验证。

## 功能特点

- 创建指定时长的卡密
- 删除已有卡密
- 查看卡密列表及状态
- API接口验证卡密有效性

## 安装说明

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 运行应用：
```bash
python app.py
```

3. 访问系统：
打开浏览器访问 http://localhost:5000

## API使用说明

### 验证卡密
- 接口：`GET /api/verify_card/<card_key>`
- 示例：`http://localhost:5000/api/verify_card/your_card_key`
- 返回格式：
```json
{
    "valid": true/false,
    "remaining_minutes": 分钟数,
    "message": "状态说明"
}
```

## 技术栈

- Flask
- SQLite
- Bootstrap 5
- Flask-SQLAlchemy 