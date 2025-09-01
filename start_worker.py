#!/usr/bin/env python3
"""
Celery Worker Startup Script for COMSOL Local Server

This script starts the Celery worker that processes COMSOL simulation tasks.
Run this script in a separate terminal/command prompt while the Flask app is running.

Usage:
    python start_worker.py

The worker will process tasks from both high_priority and normal_priority queues.
"""

import os
import sys
from pathlib import Path

# Fix for Windows Celery multiprocessing issue
os.environ['FORKED_BY_MULTIPROCESSING'] = '1'

# Add the project directory to Python path
project_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_dir))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import Celery app
from tasks import celery
import tasks  # Ensure task registration

if __name__ == '__main__':
    print("Starting COMSOL Celery Worker...")
    print(f"Project Directory: {project_dir}")
    print(f"Broker URL: {os.environ.get('CELERY_BROKER_URL', 'pyamqp://guest@localhost//')}")
    print(f"Result Backend: {os.environ.get('CELERY_RESULT_BACKEND', 'rpc://')}")
    print("\nWorker will process tasks from queues: high_priority, normal_priority")
    print("Press Ctrl+C to stop the worker\n")
    
    # Start the worker
    celery.worker_main([
        'worker',
        '--loglevel=info',
        '--queues=high_priority,normal_priority',
        '--concurrency=1',  # Process one task at a time
        '--include=tasks'
    ])
