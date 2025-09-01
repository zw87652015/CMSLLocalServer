import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from celery.app import Celery
from models import db, Task, SystemStats
from config import Config
from app import app  # Import the Flask app

# Initialize Celery
celery = Celery()

# Override the result backend to use memory instead of SQLite
celery.conf.update(
    CELERY_RESULT_BACKEND='rpc://',
    CELERY_TASK_IGNORE_RESULT=False,
    CELERY_TASK_SERIALIZER='json',
    CELERY_ACCEPT_CONTENT=['json'],
    CELERY_RESULT_SERIALIZER='json',
    CELERYD_HIJACK_ROOT_LOGGER=False
)

# Load the rest of the configuration
celery.config_from_object('config.Config')

class ProgressParser:
    """Parse COMSOL® progress output to extract percentage and current step"""
    
    @staticmethod
    def parse_progress_line(line):
        """Extract progress percentage and step from COMSOL® output line"""
        # Pattern for progress percentage: "当前进度: XX % - Step description"
        progress_pattern = r'当前进度:\s*(\d+)\s*%\s*-\s*(.+)'
        match = re.search(progress_pattern, line)
        
        if match:
            percentage = float(match.group(1))
            step = match.group(2).strip()
            return percentage, step
        
        # Pattern for completion: "当前进度: 100 % - 完成"
        if '完成' in line and '100' in line:
            return 100.0, '完成'
        
        return None, None
    
    @staticmethod
    def parse_error(output):
        """Extract error information from COMSOL® output"""
        error_patterns = [
            r'错误[:：]\s*(.+)',
            r'Error[:：]\s*(.+)',
            r'失败[:：]\s*(.+)',
            r'Failed[:：]\s*(.+)',
            r'/\*+错误\*+/',  # Error block markers like /*****错误********/
            r'以下特征遇到问题[:：]',  # "The following features encountered problems:"
            r'未定义.*所需的材料属性',  # "Required material property ... is not defined"
        ]
        
        for pattern in error_patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return match.group(1).strip() if match.groups() else "COMSOL® simulation error detected"
        
        return None
    
    @staticmethod
    def has_error_markers(output):
        """Check if output contains COMSOL® error markers"""
        error_markers = [
            r'/\*+错误\*+/',  # Error block markers
            '以下特征遇到问题',  # "The following features encountered problems"
            r'未定义.*所需的材料属性',  # Material property errors
            'ERROR',
            'FAILED'
        ]
        
        for marker in error_markers:
            if re.search(marker, output, re.IGNORECASE):
                return True
        return False

@celery.task(bind=True)
def run_comsol_simulation(self, task_id, input_file_path, output_file_path):
    """
    Execute COMSOL® simulation task
    
    Args:
        task_id: Database task ID
        input_file_path: Path to input .mph file
        output_file_path: Path for output .mph file
    """
    
    from app import create_app
    app = create_app()
    
    with app.app_context():
        # Get task from database
        task = Task.query.get(task_id)
        if not task:
            raise Exception(f"Task {task_id} not found in database")
        
        try:
            # Mark task as started
            task.mark_started()
            task.celery_task_id = self.request.id
            db.session.commit()
            
            # Prepare COMSOL® command
            comsol_cmd = [
                Config.COMSOL_EXECUTABLE,
                '-inputfile', str(input_file_path),
                '-outputfile', str(output_file_path)
            ]
            
            # Create user-specific log file path
            user_folder = task.user.get_user_folder()
            user_logs_path = Config.LOGS_FOLDER / user_folder
            user_logs_path.mkdir(parents=True, exist_ok=True)
            log_file_path = user_logs_path / f"{task.unique_filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            task.log_filename = log_file_path.name
            db.session.commit()
            
            # Start COMSOL® process
            process = subprocess.Popen(
                comsol_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            # Monitor progress
            output_lines = []
            last_progress = 0.0
            
            with open(log_file_path, 'w', encoding='utf-8') as log_file:
                for line in process.stdout:
                    line = line.strip()
                    output_lines.append(line)
                    log_file.write(line + '\n')
                    log_file.flush()
                    
                    # Parse progress
                    percentage, step = ProgressParser.parse_progress_line(line)
                    if percentage is not None:
                        if percentage > last_progress:
                            task.update_progress(percentage, step)
                            last_progress = percentage
                            
                            # Update Celery task state
                            self.update_state(
                                state='PROGRESS',
                                meta={
                                    'current': percentage,
                                    'total': 100,
                                    'status': step or 'Processing...'
                                }
                            )
            
            # Wait for process to complete
            return_code = process.wait()
            full_output = '\n'.join(output_lines)
            
            if return_code == 0:
                # Check for COMSOL® errors even if return code is 0
                if ProgressParser.has_error_markers(full_output):
                    error_msg = ProgressParser.parse_error(full_output) or "COMSOL® simulation completed with errors"
                    task.mark_failed(error_msg, full_output)
                    raise Exception(error_msg)
                
                # Success - no errors detected
                if os.path.exists(output_file_path):
                    task.mark_completed(Path(output_file_path).name)
                    return {
                        'status': 'completed',
                        'result_file': str(output_file_path),
                        'log_file': str(log_file_path),
                        'execution_time': task.execution_time
                    }
                else:
                    # Process succeeded but no output file
                    error_msg = "COMSOL® process completed but no output file was generated"
                    task.mark_failed(error_msg, full_output)
                    raise Exception(error_msg)
            else:
                # Process failed
                error_msg = ProgressParser.parse_error(full_output) or f"COMSOL® process failed with return code {return_code}"
                task.mark_failed(error_msg, full_output)
                raise Exception(error_msg)
                
        except Exception as e:
            # Handle any unexpected errors
            error_msg = str(e)
            if task:
                task.mark_failed(error_msg)
            
            # Log error to file if possible
            try:
                if 'log_file_path' in locals():
                    with open(log_file_path, 'a', encoding='utf-8') as log_file:
                        log_file.write(f"\nERROR: {error_msg}\n")
            except:
                pass
            
            raise e

@celery.task
def cleanup_old_files():
    """Clean up old result and log files"""
    import time
    from pathlib import Path
    
    # Clean files older than 7 days
    cutoff_time = time.time() - (7 * 24 * 60 * 60)
    
    for folder in [Config.RESULTS_FOLDER, Config.LOGS_FOLDER]:
        if folder.exists():
            for file_path in folder.iterdir():
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                    except Exception as e:
                        print(f"Failed to delete {file_path}: {e}")

@celery.task
def update_system_stats():
    """Update system statistics"""
    import psutil
    from models import SystemStats
    
    with app.app_context():
        # Get current task counts
        pending_count = Task.query.filter_by(status='pending').count()
        running_count = Task.query.filter_by(status='running').count()
        
        # Get today's completed/failed tasks
        today = datetime.now().date()
        completed_today = Task.query.filter(
            Task.status == 'completed',
            Task.completed_at >= today
        ).count()
        
        failed_today = Task.query.filter(
            Task.status == 'failed',
            Task.completed_at >= today
        ).count()
        
        # Get system resource usage
        cpu_usage = psutil.cpu_percent()
        memory_usage = psutil.virtual_memory().percent
        disk_usage = psutil.disk_usage('/').percent
        
        # Calculate average times
        recent_tasks = Task.query.filter(
            Task.completed_at >= today,
            Task.execution_time.isnot(None)
        ).all()
        
        avg_queue_time = sum(t.queue_time for t in recent_tasks if t.queue_time) / len(recent_tasks) if recent_tasks else 0
        avg_execution_time = sum(t.execution_time for t in recent_tasks) / len(recent_tasks) if recent_tasks else 0
        
        # Create new stats record
        stats = SystemStats(
            pending_tasks=pending_count,
            running_tasks=running_count,
            completed_tasks_today=completed_today,
            failed_tasks_today=failed_today,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            disk_usage=disk_usage,
            avg_queue_time=avg_queue_time,
            avg_execution_time=avg_execution_time
        )
        
        db.session.add(stats)
        db.session.commit()
        
        return {
            'pending': pending_count,
            'running': running_count,
            'completed_today': completed_today,
            'failed_today': failed_today
        }
