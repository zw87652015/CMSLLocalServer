# 分布式仿真任务管理系统

[English](README_EN.md) | [中文](README.md)

**免责声明**: 本项目是独立开发的第三方工具，与COMSOL® AB公司无关。COMSOL® 和 COMSOL® Multiphysics 是COMSOL® AB的注册商标。

基于Flask和Celery的局域网仿真任务管理系统，专为COMSOL® Multiphysics设计。支持从任意浏览器上传`.mph`文件，自动分发到服务器本机或多台计算节点运行，完成后下载结果。

---

## 功能特性

- **用户管理** — 登录、注册、管理员面板、密码策略
- **任务队列** — 基于RabbitMQ/Celery，支持普通和高优先级
- **分布式节点** — 通过`node_client.py`在局域网内其他Windows主机上运行仿真；节点自动注册、领取任务、上报进度
- **节点监控** — 实时显示每个节点的状态、CPU型号、核心数、磁盘剩余空间
- **自动恢复** — 节点断线时立即重新排队正在运行的任务，自动分配到其他可用节点或本机
- **实时进度** — 每个任务的进度条和当前步骤，实时更新
- **结果交付** — 直接下载；结果文件过大无法上传时，服务器可按需向节点请求重新上传
- **取消任务重排** — 已取消的任务无需重新上传文件即可重新排队
- **日志查看** — 浏览器内查看完整COMSOL输出日志，包括节点运行的任务和中途中止的任务
- **管理员面板** — 管理用户、查看所有任务、管理节点注册
- **双语界面** — 中英文自动切换

---

## 系统要求

- Python 3.8+
- RabbitMQ（本地或远程）
- COMSOL® Multiphysics 6.2 或 6.3（安装在运行仿真的每台主机上）

---

## 快速开始（服务器端）

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置环境变量
复制`.env.example`为`.env`并编辑：
```ini
# RabbitMQ消息代理
CELERY_BROKER_URL=pyamqp://guest:guest@localhost:5672//

# COMSOL®可执行文件路径（本机运行时使用）
COMSOL_63=C:\Program Files\COMSOL\COMSOL63\Multiphysics\bin\win64\comsolbatch.exe
COMSOL_62=C:\Program Files\COMSOL\COMSOL62\Multiphysics\bin\win64\comsolbatch.exe
```

### 3. 初始化数据库
**全新安装：**
```bash
python -c "from app import create_app; app=create_app(); ctx=app.app_context(); ctx.push(); from models import db; db.create_all()"
```

**从旧版本升级：**
```bash
python db_migration.py
```

### 4. 启动系统

**Windows（推荐）：**
```bash
start_system.bat
```
该脚本会自动打开两个终端，分别运行Flask服务器和Celery Worker。

**手动启动：**
```bash
# 终端1 — Flask服务器
python app.py

# 终端2 — Celery Worker（每次处理一个任务）
python start_worker.py
```

访问地址：`http://localhost:5000`  
默认管理员账号：`admin` / `admin123` — 首次登录后请立即修改密码。

---

## 添加计算节点

局域网内任意Windows主机均可作为计算节点。

### 1. 复制文件到节点主机
将`node_client.py`复制到节点计算机。

### 2. 在节点上安装依赖
```bash
pip install requests psutil
```

### 3. 运行节点客户端
```bash
python node_client.py --server http://<服务器IP>:5000
```

可选 — 指定非默认的COMSOL路径：
```bash
python node_client.py --server http://<服务器IP>:5000 ^
    --comsol-63 "D:\COMSOL63\bin\win64\comsolbatch.exe" ^
    --comsol-62 "D:\COMSOL62\bin\win64\comsolbatch.exe"
```

节点将自动注册，15秒内出现在管理员**节点计算机**页面。认证信息保存在`node_client_config.json`（已加入.gitignore），重启后自动复用。

### 节点工作机制
- 每15秒发送一次心跳；服务器60秒未收到心跳则标记节点离线
- 自动领取与其COMSOL版本匹配的待执行任务
- 每次只运行一个任务
- 完成后上传结果文件；若文件过大，服务器可按需请求重新上传
- 关闭时发送离线信号，任务立即重新排队

---

## 项目结构

```
CMSLLocalServer/
├── app.py                  # Flask主应用及所有路由
├── tasks.py                # Celery任务定义
├── models.py               # SQLAlchemy数据库模型
├── config.py               # 配置
├── node_client.py          # 节点计算客户端（复制到工作节点主机）
├── db_migration.py         # 增量数据库迁移脚本
├── start_worker.py         # Celery Worker启动脚本
├── start_system.bat        # Windows一键启动脚本
├── requirements.txt
├── .env                    # 环境变量（不提交到版本库）
├── database.db             # SQLite数据库
├── uploads/
│   └── user_<id>/          # 用户专属上传目录
├── results/
│   └── user_<id>/          # 用户专属结果目录
├── logs/
│   └── user_<id>/          # 用户专属日志目录
├── templates/
│   ├── admin/
│   │   ├── dashboard.html
│   │   ├── users.html
│   │   ├── tasks.html
│   │   └── nodes.html
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── history.html
│   └── queue.html
└── static/
    ├── style.css
    ├── script.js
    └── favicon.ico
```

---

## API接口

除特别说明外，所有接口均需登录。

### 用户
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/login` | 登录 |
| POST | `/logout` | 登出 |
| POST | `/register` | 注册新账号 |

### 任务
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/upload` | 上传`.mph`文件并排队 |
| GET | `/tasks` | 获取当前用户任务列表（JSON） |
| GET | `/task/<id>/status` | 获取任务状态和节点信息（JSON） |
| POST | `/task/<id>/cancel` | 取消运行中或排队中的任务 |
| POST | `/task/<id>/requeue` | 重新排队已取消的任务 |
| DELETE | `/task/<id>/delete` | 删除任务及相关文件 |
| GET | `/download/<id>` | 下载结果文件 |
| GET | `/task/<id>/logs` | 查看任务日志 |

### 系统
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/queue` | 队列状态页面 |
| GET | `/history` | 任务历史页面 |
| GET | `/api/stats` | 系统统计信息（JSON） |

### 节点API（需携带`X-Node-Id`和`X-Node-Token`请求头）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/nodes/register` | 节点注册 |
| POST | `/api/nodes/heartbeat` | 心跳/状态更新 |
| GET | `/api/nodes/task/poll` | 领取下一个可用任务 |
| GET | `/api/nodes/task/<id>/file` | 下载输入文件 |
| POST | `/api/nodes/task/<id>/start` | 上报任务开始 |
| POST | `/api/nodes/task/<id>/progress` | 上报进度 |
| POST | `/api/nodes/task/<id>/complete` | 上报完成并上传日志 |
| POST | `/api/nodes/task/<id>/fail` | 上报失败 |
| POST | `/api/nodes/task/<id>/upload_result` | 上传结果文件 |
| POST | `/api/nodes/task/<id>/upload_log` | 上传部分日志（中途中止的任务） |
| POST | `/api/nodes/actions/done` | 确认已完成的挂起操作 |

---

## 常见问题

**RabbitMQ连接失败**
确认RabbitMQ服务正在运行：`rabbitmq-server start`（或检查Windows服务）。

**取消任务时Celery日志出现PermissionError**
这是Windows已知问题 — Celery的`terminate=True`需要管理员权限。任务通过`psutil`终止，该错误不影响功能，已在代码中处理。

**节点断线后任务仍显示运行中**
心跳监控器将在60秒内重新排队超时任务。正常关闭节点客户端时会立即发送离线信号，任务将立刻重新排队。

**节点未显示CPU型号**
重启节点客户端 — 启动时重新注册并从Windows注册表读取CPU型号（`HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0\ProcessorNameString`）。

**任务显示为失败而非取消**
已修复 — COMSOL退出码15（取消时由psutil终止）现已正确忽略。

**升级后出现数据库列错误**
运行`python db_migration.py`为现有数据库应用新的结构变更。

---

## 许可证

MIT License
