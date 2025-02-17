# 极简卡密管理系统

## 项目简介

这是一个轻量级的卡密管理系统，专为需要灵活授权和访问控制的应用场景而设计。系统提供直观的Web界面和强大的API接口，让卡密管理变得简单高效。

## 功能特点

- 🔑 灵活创建具有指定时长的卡密
- 🗑️ 快速删除已有卡密
- 📋 实时查看卡密列表及状态
- 🔐 提供安全的API接口验证卡密
- 🕒 精确监控卡密使用情况

## 系统要求

- Python 3.8+
- pip包管理器
- 现代浏览器（Chrome、Firefox、Safari等）

## 安装步骤

### 克隆项目
```bash
git clone https://github.com/xzz0081/Minimalist-card-secret-management-system.git
cd Minimalist-card-secret-management-system
```

### 安装依赖
```bash
pip install -r requirements.txt
```

### 初始化数据库
```bash
python init_db.py
```

### 启动应用
```bash
python app.py
```

## 使用指南

### Web管理界面
1. 打开浏览器，访问 `http://localhost:5000`
2. 通过直观的界面创建、管理和监控卡密

### API接口

#### 卡密验证
- 接口：`GET /api/verify_card/<card_key>`
- 调用示例：`http://localhost:5000/api/verify_card/your_card_key`
- 返回结果示例：
```json
{
    "valid": true,
    "remaining_minutes": 120,
    "message": "卡密有效"
}
```

## 技术栈

- 后端框架：Flask
- 数据库：SQLite
- 前端框架：Bootstrap 5
- ORM：Flask-SQLAlchemy

## 安全特性

- 卡密加密存储
- API调用频率限制
- 防重复和无效卡密机制
- 安全的用户认证流程

## 贡献指南

欢迎提交 Issues 和 Pull Requests！

### 贡献流程
1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交代码变更 (`git commit -m '添加了某某特性'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

## 许可证

本项目采用 MIT 开源许可证，详情请查看 `LICENSE` 文件。

## 联系我们

如有任何问题、建议或合作意向，请：
- 提交 GitHub Issues

- 加入我们的技术交流群  电报 https://t.me/handou8808

## 项目状态

![构建状态](https://img.shields.io/badge/build-passing-brightgreen)
![版本](https://img.shields.io/badge/version-1.0.0-blue)
![覆盖率](https://img.shields.io/badge/coverage-90%25-green)

**希望这个系统能帮助你轻松管理卡密！**
