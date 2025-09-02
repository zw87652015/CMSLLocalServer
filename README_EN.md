# COMSOL® Batch Simulation Server

[English](README_EN.md) | [中文](README.md)

**Disclaimer**: This project is an independently developed third-party tool and is not associated with COMSOL® AB. COMSOL® and COMSOL® Multiphysics are registered trademarks of COMSOL® AB.

A web-based interface for running COMSOL® simulations in batch mode, with task queuing and user management.

## Features
- 🧑 User authentication (login, registration, password change)
- 👮 Admin panel for user and task management
- ⬆️ Upload COMSOL® .mph files and run simulations
- 📊 Real-time task queue and progress monitoring
- ⏹️ Cancel running tasks and automatic queue progression
- ⬇️ Download simulation results
- 📈 System resource monitoring (CPU, memory, disk)
- 🇨🇳 Supports Chinese and English file names and paths

## Installation
```bash
# Clone repository
git clone https://github.com/yourusername/CMSLLocalServer.git
cd CMSLLocalServer

# Create and activate conda environment
conda env create -f environment.yml
conda activate cmsl-server

# Install dependencies
pip install -r requirements.txt
```

## Configuration
1. Copy `.env.example` to `.env`
2. Update configuration values:
```ini
# COMSOL® executable path
COMSOL_EXECUTABLE=C:\Program Files\COMSOL\COMSOL63\Multiphysics\bin\win64\comsolbatch.exe

# Celery message broker
CELERY_BROKER_URL=pyamqp://guest:guest@localhost:5672//
```

## Running the System
```bash
# Start Redis message broker (in separate terminal)
redis-server

# Start Flask app (in separate terminal)
python start_system.py

# Start Celery worker (in separate terminal)
python start_worker.py

# Or use batch script (Windows)
start_server.bat
```

## API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/upload` | POST | Upload simulation file |
| `/tasks` | GET | Get user's tasks |
| `/task/<id>/cancel` | POST | Cancel a task |
| `/logs/<id>` | GET | View task logs |

## License
MIT License - See [LICENSE](LICENSE) for details
