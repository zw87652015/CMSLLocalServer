# 分布式仿真任务管理系统

[English](README_EN.md) | [中文](README.md)

一个基于Flask和Celery的局域网仿真任务管理系统，专为COMSOL® Multiphysics设计，支持文件上传、任务队列、实时监控和结果下载。

**免责声明**: 本项目是独立开发的第三方工具，与COMSOL® AB公司无关。COMSOL®和COMSOL® Multiphysics是COMSOL® AB的注册商标。

## 功能特性

- **用户管理**: 基于用户名/密码的身份验证系统，支持管理员权限
- **文件上传**: 支持.mph文件上传和唯一文件名生成  
- **任务队列**: 基于RabbitMQ和Celery的分布式任务处理
- **实时监控**: 任务进度实时显示和状态更新
- **优先级管理**: 支持普通和高优先级任务
- **智能错误检测**: 检测COMSOL®仿真错误并正确标记任务状态
- **完整文件管理**: 自动清理上传文件、结果文件(.mph/.recovery/.status)和日志
- **历史记录**: 完整的任务历史和执行统计
- **系统监控**: CPU、内存、磁盘使用率监控
- **Windows兼容**: 完美支持Windows环境下的Celery多进程

## 系统要求

### 软件依赖
- Python 3.8+
- RabbitMQ Server
- COMSOL® Multiphysics 6.2+ (在工作节点上)

### Python包依赖
```bash
pip install -r requirements.txt
```

### Windows特殊要求
- 系统已配置`FORKED_BY_MULTIPROCESSING=1`环境变量解决Celery兼容性问题

## 安装配置

### 1. 安装RabbitMQ
```bash
# Windows (使用Chocolatey)
choco install rabbitmq

# 或下载安装包
# https://www.rabbitmq.com/download.html

# Linux (Ubuntu/Debian)
sudo apt-get install rabbitmq-server

# 启动RabbitMQ服务
sudo systemctl start rabbitmq-server
```

### 2. 配置环境变量
复制并编辑`.env`文件：
```bash
cp .env.example .env
```

关键配置项：
- `COMSOL_EXECUTABLE`: COMSOL®批处理程序路径
- `CELERY_BROKER_URL`: RabbitMQ连接URL
- `MAX_CONCURRENT_TASKS`: 最大并发任务数

### 3. 初始化数据库
```bash
# 如果是全新安装
python -c "from app import create_app; app = create_app(); app.app_context().push(); from models import db; db.create_all()"

# 如果从旧版本升级，运行数据库迁移
python migrate_db.py
```

## 运行系统

### 1. 启动Flask Web服务器
```bash
python app.py
```
访问: http://localhost:5000

### 2. 启动Celery Worker
```bash
# 推荐方式：使用提供的启动脚本
python start_worker.py

# 或手动启动
celery -A tasks worker --loglevel=info --queues=high_priority,normal_priority --concurrency=1 --include=tasks
```

### 3. 启动定时任务 (可选)
```bash
celery -A tasks beat --loglevel=info
```

### 4. 使用批处理脚本启动 (Windows)

我们提供了一个批处理脚本 `start_system.bat` 用于在Windows上方便地启动系统。该脚本会自动检测并激活Conda环境（如果可用），然后启动Flask服务器和Celery worker。

使用方法：
1. 双击运行 `start_system.bat`
2. 根据提示选择是否使用Conda环境（如果系统检测到Conda）
3. 脚本将自动打开两个终端窗口分别运行Flask和Celery

注意：使用前请确保已安装RabbitMQ并配置好环境变量。

## 使用说明

### 用户注册和登录
1. 首次使用需要注册账户（用户名/密码）
2. 管理员账户会自动创建：
   - 用户名：`admin`
   - 密码：`admin123`（建议首次登录后修改）
3. 普通用户可以通过注册页面创建账户

### 上传仿真文件
1. 登录后访问主页面
2. 选择.mph文件
3. 设置任务优先级
4. 点击"上传并开始仿真"

### 监控任务状态
- **首页**: 查看个人任务和系统状态
- **历史记录**: 查看完整任务历史
- **队列状态**: 查看全局队列和系统资源
- **管理员面板**: 管理员可以查看所有用户和任务

### 下载结果
- 任务完成后，点击"下载"按钮获取结果文件
- 点击"日志"按钮查看详细执行日志

## 项目结构

```
CMSLLocalServer/
├── app.py                  # Flask主应用
├── tasks.py                # Celery任务定义
├── models.py               # 数据库模型
├── config.py               # 配置文件
├── start_worker.py         # Celery Worker启动脚本
├── start_system.bat        # Windows批处理脚本
├── requirements.txt        # Python依赖
├── .env                    # 环境变量
├── database.db             # SQLite数据库
├── uploads/                # 上传文件存储
│   └── user_[username]/    # 用户专属上传目录
├── results/                # 结果文件存储 (.mph/.recovery/.status)
│   └── user_[username]/    # 用户专属结果目录
├── logs/                   # 任务执行日志
│   └── user_[username]/    # 用户专属日志目录
├── templates/              # HTML模板
│   ├── admin/              # 管理员模板
│   │   ├── dashboard.html
│   │   ├── users.html
│   │   └── tasks.html
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── history.html
│   └── queue.html
└── static/                 # 静态资源
    ├── style.css
    ├── script.js
    └── favicon.ico
```

## API接口

**注意**: 所有API接口都需要用户登录认证

### 用户认证
```
POST /login
Content-Type: application/x-www-form-urlencoded
Body: username, password

POST /register
Content-Type: application/x-www-form-urlencoded
Body: username, password, confirm_password

POST /logout
```

### 文件上传
```
POST /upload
Content-Type: multipart/form-data
Body: file, priority
Headers: Authentication required
```

### 获取任务列表
```
GET /tasks
Response: JSON array of tasks
```

### 获取任务状态
```
GET /task/<task_id>/status
Response: JSON task details
```

### 下载结果文件
```
GET /download/<task_id>
Response: File download
```

### 系统统计
```
GET /api/stats
Response: JSON system statistics
```

## 故障排除

### 常见问题

1. **Windows Celery错误 "ValueError: not enough values to unpack"**
   - 已通过设置`FORKED_BY_MULTIPROCESSING=1`环境变量解决
   - 使用提供的`start_worker.py`脚本启动

2. **RabbitMQ连接失败**
   - 检查RabbitMQ服务是否运行
   - 验证连接URL配置

3. **COMSOL®执行失败**
   - 检查COMSOL®路径配置
   - 验证文件权限
   - 查看任务日志

4. **文件上传失败**
   - 检查文件大小限制
   - 验证文件格式
   - 检查磁盘空间

5. **任务显示为成功但实际有错误**
   - 系统已增强错误检测，能识别COMSOL®中文错误信息
   - 检查任务日志查看详细错误信息

6. **日志文件找不到**
   - 确保已从旧版本正确迁移到用户系统
   - 日志现在存储在用户专属目录中：`logs/user_[username]/`
   - 运行 `python migrate_db.py` 确保数据库架构正确

### 日志查看
- 应用日志: Flask控制台输出
- 任务日志: `logs/user_[username]/`目录下的文件
- Celery日志: Worker控制台输出

## 扩展部署

### 多机部署
1. 在每台工作机器上安装COMSOL®
2. 配置相同的RabbitMQ连接
3. 启动Celery Worker
4. Web服务器可以单独部署

### 负载均衡
- 使用Nginx进行Web服务负载均衡
- RabbitMQ集群提高可用性
- 数据库可迁移到PostgreSQL/MySQL

## 许可证

本项目基于MIT许可证开源。
