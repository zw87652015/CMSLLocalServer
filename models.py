from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to tasks
    tasks = db.relationship('Task', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)
    
    def get_user_folder(self):
        """Get user-specific folder path"""
        return f"user_{self.username}"
    
    def is_administrator(self):
        """Check if user is admin"""
        return self.is_admin
    
    def deactivate(self):
        """Deactivate user account"""
        self.is_active = False
        db.session.commit()
    
    def activate(self):
        """Activate user account"""
        self.is_active = True
        db.session.commit()
    
    def __repr__(self):
        return f'<User {self.username}>'

class Task(db.Model):
    __tablename__ = 'tasks'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    
    # File information
    original_filename = db.Column(db.String(255), nullable=False)
    unique_filename = db.Column(db.String(255), nullable=False, unique=True)
    file_size = db.Column(db.Integer)
    
    # Task status and timing
    status = db.Column(db.String(50), default='pending')  # pending, queued, running, completed, failed
    priority = db.Column(db.String(20), default='normal')  # normal, high
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    queued_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Progress and results
    progress_percentage = db.Column(db.Float, default=0.0)
    current_step = db.Column(db.String(255))
    
    # Execution details
    celery_task_id = db.Column(db.String(255))
    execution_time = db.Column(db.Float)  # in seconds
    queue_time = db.Column(db.Float)  # in seconds
    
    # Error handling
    error_message = db.Column(db.Text)
    error_log = db.Column(db.Text)
    
    # Result files
    result_filename = db.Column(db.String(255))
    log_filename = db.Column(db.String(255))
    
    def __repr__(self):
        return f'<Task {self.id}: {self.original_filename}>'
    
    @property
    def is_active(self):
        return self.status in ['queued', 'running']
    
    @property
    def is_completed(self):
        return self.status in ['completed', 'failed']
    
    def update_progress(self, percentage, step=None):
        self.progress_percentage = percentage
        if step:
            self.current_step = step
        db.session.commit()
    
    def mark_queued(self):
        self.status = 'queued'
        self.queued_at = datetime.utcnow()
        if self.created_at:
            self.queue_time = (self.queued_at - self.created_at).total_seconds()
        db.session.commit()
    
    def mark_started(self):
        self.status = 'running'
        self.started_at = datetime.utcnow()
        db.session.commit()
    
    def mark_completed(self, result_filename=None):
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        self.progress_percentage = 100.0
        if result_filename:
            self.result_filename = result_filename
        if self.started_at:
            self.execution_time = (self.completed_at - self.started_at).total_seconds()
        db.session.commit()
    
    def mark_failed(self, error_message=None, error_log=None):
        self.status = 'failed'
        self.completed_at = datetime.utcnow()
        if error_message:
            self.error_message = error_message
        if error_log:
            self.error_log = error_log
        if self.started_at:
            self.execution_time = (self.completed_at - self.started_at).total_seconds()
        db.session.commit()
    
    def mark_cancelled(self):
        """Mark task as cancelled"""
        self.status = 'cancelled'
        self.completed_at = datetime.utcnow()
        if self.started_at:
            self.execution_time = (self.completed_at - self.started_at).total_seconds()
        db.session.commit()
    
    def can_be_cancelled(self):
        """Check if task can be cancelled"""
        return self.status in ['pending', 'queued', 'running']
    
    def cleanup_files(self):
        """Clean up associated files when task is deleted"""
        from config import Config
        import os
        from pathlib import Path
        
        # Clean up upload file
        upload_path = Config.UPLOAD_FOLDER / self.unique_filename
        if upload_path.exists():
            try:
                os.remove(upload_path)
            except Exception:
                pass
        
        # Clean up result file and its related files (.mph.recovery, .mph.status)
        if self.result_filename:
            result_path = Config.RESULTS_FOLDER / self.result_filename
            
            # Remove main result file
            if result_path.exists():
                try:
                    os.remove(result_path)
                except Exception:
                    pass
            
            # Remove recovery file (.mph.recovery)
            recovery_path = Path(str(result_path) + '.recovery')
            if recovery_path.exists():
                try:
                    os.remove(recovery_path)
                except Exception:
                    pass
            
            # Remove status file (.mph.status)
            status_path = Path(str(result_path) + '.status')
            if status_path.exists():
                try:
                    os.remove(status_path)
                except Exception:
                    pass
        
        # Also check for result files based on unique_filename pattern (for failed tasks)
        # Pattern: {unique_filename_stem}_solved.mph
        if self.unique_filename:
            unique_stem = Path(self.unique_filename).stem
            result_pattern = f"{unique_stem}_solved.mph"
            result_path = Config.RESULTS_FOLDER / result_pattern
            
            # Remove main result file
            if result_path.exists():
                try:
                    os.remove(result_path)
                except Exception:
                    pass
            
            # Remove recovery file (.mph.recovery)
            recovery_path = Path(str(result_path) + '.recovery')
            if recovery_path.exists():
                try:
                    os.remove(recovery_path)
                except Exception:
                    pass
            
            # Remove status file (.mph.status)
            status_path = Path(str(result_path) + '.status')
            if status_path.exists():
                try:
                    os.remove(status_path)
                except Exception:
                    pass
        
        # Clean up log file
        if self.log_filename:
            user_folder = self.user.get_user_folder()
            log_path = Config.LOGS_FOLDER / user_folder / self.log_filename
            if log_path.exists():
                try:
                    os.remove(log_path)
                except Exception:
                    pass

class SystemStats(db.Model):
    __tablename__ = 'system_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Queue statistics
    pending_tasks = db.Column(db.Integer, default=0)
    running_tasks = db.Column(db.Integer, default=0)
    completed_tasks_today = db.Column(db.Integer, default=0)
    failed_tasks_today = db.Column(db.Integer, default=0)
    
    # System resources
    cpu_usage = db.Column(db.Float)
    memory_usage = db.Column(db.Float)
    disk_usage = db.Column(db.Float)
    
    # Average times
    avg_queue_time = db.Column(db.Float)
    avg_execution_time = db.Column(db.Float)
    
    def __repr__(self):
        return f'<SystemStats {self.timestamp}>'
