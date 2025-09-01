import os
from pathlib import Path

class Config:
    # Base directory
    BASE_DIR = Path(__file__).parent.absolute()
    
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'database.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Celery configuration
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or 'pyamqp://guest@localhost//'
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or 'rpc://'
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TIMEZONE = 'Asia/Shanghai'  # Keep using old-style setting name
    BROKER_CONNECTION_RETRY_ON_STARTUP = True  # Using old-style setting name
    CELERY_IMPORTS = ('tasks',)   # Add this
    
    # File upload configuration
    UPLOAD_FOLDER = BASE_DIR / 'uploads'
    RESULTS_FOLDER = BASE_DIR / 'results'
    LOGS_FOLDER = BASE_DIR / 'logs'
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size
    ALLOWED_EXTENSIONS = {'mph'}
    
    # COMSOL configuration
    COMSOL_EXECUTABLE = os.environ.get('COMSOL_EXECUTABLE') or r'D:\Program Files\COMSOL\COMSOL62\Multiphysics\bin\win64\comsolbatch.exe'
    
    # Task queue configuration
    MAX_CONCURRENT_TASKS = int(os.environ.get('MAX_CONCURRENT_TASKS', 2))
    HIGH_PRIORITY_QUEUE = 'high_priority'
    NORMAL_PRIORITY_QUEUE = 'normal_priority'
    
    # Monitoring configuration
    PROGRESS_UPDATE_INTERVAL = 5  # seconds
    TASK_TIMEOUT = 3600  # 1 hour in seconds
    
    @staticmethod
    def init_app(app):
        # Create directories if they don't exist
        for folder in [Config.UPLOAD_FOLDER, Config.RESULTS_FOLDER, Config.LOGS_FOLDER]:
            folder.mkdir(exist_ok=True)
