# COMSOL® Batch Simulation Server

[English](README_EN.md) | [中文](README.md)

**Disclaimer**: This project is an independently developed third-party tool and is not affiliated with COMSOL® AB. COMSOL® and COMSOL® Multiphysics are registered trademarks of COMSOL® AB.

A LAN-based web server for managing and distributing COMSOL® batch simulations. Upload `.mph` files from any browser, have them run automatically on the server or across multiple compute nodes, and download results when done.

---

## Features

- **User management** — login, registration, admin panel, password enforcement
- **Task queue** — RabbitMQ/Celery-backed queue with normal and high priority
- **Distributed nodes** — run simulations on remote Windows machines via `node_client.py`; nodes register themselves, claim tasks, and report progress automatically
- **Node monitoring** — live status, CPU model, core count, disk free space per node
- **Automatic recovery** — tasks re-queued instantly when a node goes offline mid-run; reassigned to another available node or the local server
- **Real-time progress** — per-task progress bar and step description, updated live
- **Result delivery** — direct download; if a result file is too large to upload, the server requests a re-upload from the node on demand
- **Cancelled task re-queue** — cancelled tasks can be re-submitted without re-uploading the file
- **Log access** — full COMSOL output log viewable in-browser for every task, including tasks run on remote nodes and aborted tasks
- **Admin panel** — manage users, view all tasks, inspect node registrations
- **Bilingual UI** — Chinese and English, auto-detected from browser

---

## Requirements

- Python 3.8+
- RabbitMQ (local or remote)
- COMSOL® Multiphysics 6.2 or 6.3 (on each machine that runs simulations)

---

## Quick Start (Server)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
Copy `.env.example` to `.env` and edit:
```ini
# RabbitMQ broker
CELERY_BROKER_URL=pyamqp://guest:guest@localhost:5672//

# COMSOL® executables (used when running locally)
COMSOL_63=C:\Program Files\COMSOL\COMSOL63\Multiphysics\bin\win64\comsolbatch.exe
COMSOL_62=C:\Program Files\COMSOL\COMSOL62\Multiphysics\bin\win64\comsolbatch.exe
```

### 3. Initialise the database
**Fresh install:**
```bash
python -c "from app import create_app; app=create_app(); ctx=app.app_context(); ctx.push(); from models import db; db.create_all()"
```

**Upgrade existing database:**
```bash
python db_migration.py
```

### 4. Start the system

**Windows (recommended):**
```bash
start_system.bat
```
This opens two terminals — one for Flask, one for the Celery worker.

**Manual:**
```bash
# Terminal 1 — Flask server
python app.py

# Terminal 2 — Celery worker (one task at a time)
python start_worker.py
```

Access the web interface at `http://localhost:5000`.  
Default admin credentials: `admin` / `admin123` — change on first login.

---

## Adding Compute Nodes

Any Windows machine on the same network can act as a compute node.

### 1. Copy files to the node machine
Copy `node_client.py` to the node computer.

### 2. Install dependencies on the node
```bash
pip install requests psutil
```

### 3. Run the node client
```bash
python node_client.py --server http://<server-ip>:5000
```

Optional — specify non-default COMSOL paths:
```bash
python node_client.py --server http://<server-ip>:5000 ^
    --comsol-63 "D:\COMSOL63\bin\win64\comsolbatch.exe" ^
    --comsol-62 "D:\COMSOL62\bin\win64\comsolbatch.exe"
```

The node registers itself automatically and appears in the admin **Node Computers** page within 15 seconds. Credentials are saved to `node_client_config.json` (gitignored) and reused on restart.

### Node behaviour
- Sends a heartbeat every 15 s; server marks it offline after 60 s of silence
- Polls for available tasks matching its COMSOL version(s)
- Runs one task at a time
- Uploads the result file on completion; if the file is too large, the server can request a re-upload later
- On shutdown, sends an offline signal so tasks are immediately re-queued

---

## Project Structure

```
CMSLLocalServer/
├── app.py                  # Flask application and all routes
├── tasks.py                # Celery task definitions
├── models.py               # SQLAlchemy database models
├── config.py               # Configuration
├── node_client.py          # Node compute client (copy to worker machines)
├── db_migration.py         # Incremental database migration script
├── start_worker.py         # Celery worker launcher
├── start_system.bat        # Windows one-click startup script
├── requirements.txt
├── .env                    # Environment variables (not committed)
├── database.db             # SQLite database
├── uploads/
│   └── user_<id>/          # Per-user upload storage
├── results/
│   └── user_<id>/          # Per-user result storage
├── logs/
│   └── user_<id>/          # Per-user task log storage
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

## API Reference

All endpoints require login unless noted.

### User
| Method | Path | Description |
|--------|------|-------------|
| POST | `/login` | Log in |
| POST | `/logout` | Log out |
| POST | `/register` | Register new account |

### Tasks
| Method | Path | Description |
|--------|------|-------------|
| POST | `/upload` | Upload `.mph` file and queue simulation |
| GET | `/tasks` | List current user's tasks (JSON) |
| GET | `/task/<id>/status` | Task status and node info (JSON) |
| POST | `/task/<id>/cancel` | Cancel running or queued task |
| POST | `/task/<id>/requeue` | Re-queue a cancelled task |
| DELETE | `/task/<id>/delete` | Delete task and files |
| GET | `/download/<id>` | Download result file |
| GET | `/task/<id>/logs` | View task log |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/queue` | Queue status page |
| GET | `/history` | Task history page |
| GET | `/api/stats` | System statistics (JSON) |

### Node API (`X-Node-Id` + `X-Node-Token` headers required)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/nodes/register` | Node registration |
| POST | `/api/nodes/heartbeat` | Heartbeat / status update |
| GET | `/api/nodes/task/poll` | Claim next available task |
| GET | `/api/nodes/task/<id>/file` | Download input file |
| POST | `/api/nodes/task/<id>/start` | Report task started |
| POST | `/api/nodes/task/<id>/progress` | Report progress |
| POST | `/api/nodes/task/<id>/complete` | Report completion + upload log |
| POST | `/api/nodes/task/<id>/fail` | Report failure |
| POST | `/api/nodes/task/<id>/upload_result` | Upload result file |
| POST | `/api/nodes/task/<id>/upload_log` | Upload partial log (aborted tasks) |
| POST | `/api/nodes/actions/done` | Acknowledge completed pending actions |

---

## Troubleshooting

**RabbitMQ connection refused**
Ensure RabbitMQ is running: `rabbitmq-server start` (or check Windows Services).

**`PermissionError` in Celery logs on task cancel**
Expected on Windows — Celery's `terminate=True` requires admin rights. Tasks are killed via `psutil` instead; the error is harmless and has been suppressed.

**Task stuck as Running after node disconnected**
The heartbeat monitor re-queues stale tasks within 60 s. For immediate recovery, the node sends an offline signal on clean shutdown.

**CPU model not showing for a node**
Restart the node client — it re-registers on startup and reads the CPU model from the Windows registry (`HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0\ProcessorNameString`).

**Task shows Failed instead of Cancelled**
Fixed in current version — COMSOL exit code 15 (killed by psutil on cancel) is now correctly ignored when the task is already marked cancelled.

**Database column errors after update**
Run `python db_migration.py` to apply any new schema changes to an existing database.

---

## License

MIT License
