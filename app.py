import os
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, request, render_template, jsonify, send_file, session
from werkzeug.utils import secure_filename
from models import db, User, Task, SystemStats
from config import Config
# Import moved to avoid circular import

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    Config.init_app(app)
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    return app

app = create_app()

def get_or_create_user():
    """Get or create user based on browser fingerprint"""
    # Create a simple browser fingerprint
    user_agent = request.headers.get('User-Agent', '')
    ip_address = request.remote_addr
    fingerprint = hashlib.md5(f"{user_agent}_{ip_address}".encode()).hexdigest()
    
    user = User.query.filter_by(browser_fingerprint=fingerprint).first()
    if not user:
        user = User(browser_fingerprint=fingerprint)
        db.session.add(user)
        db.session.commit()
    else:
        user.last_seen = datetime.utcnow()
        db.session.commit()
    
    return user

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def generate_unique_filename(original_filename):
    """Generate unique filename while preserving extension"""
    name, ext = os.path.splitext(original_filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    return f"{name}_{timestamp}_{unique_id}{ext}"

@app.route('/')
def index():
    """Main page - file upload and task monitoring"""
    user = get_or_create_user()
    recent_tasks = Task.query.filter_by(user_id=user.id).order_by(Task.created_at.desc()).limit(10).all()
    return render_template('index.html', tasks=recent_tasks)

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and queue simulation task"""
    user = get_or_create_user()
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Only .mph files are allowed'}), 400
    
    try:
        # Generate unique filename
        original_filename = secure_filename(file.filename)
        unique_filename = generate_unique_filename(original_filename)
        
        # Save uploaded file
        upload_path = Config.UPLOAD_FOLDER / unique_filename
        file.save(upload_path)
        
        # Get priority from form
        priority = request.form.get('priority', 'normal')
        
        # Create task record
        task = Task(
            user_id=user.id,
            original_filename=original_filename,
            unique_filename=unique_filename,
            file_size=upload_path.stat().st_size,
            priority=priority
        )
        db.session.add(task)
        db.session.commit()
        
        # Queue Celery task
        result_filename = f"{Path(unique_filename).stem}_solved.mph"
        result_path = Config.RESULTS_FOLDER / result_filename
        
        from tasks import run_comsol_simulation
        celery_task = run_comsol_simulation.apply_async(
            args=[task.id, str(upload_path), str(result_path)],
            queue=Config.HIGH_PRIORITY_QUEUE if priority == 'high' else Config.NORMAL_PRIORITY_QUEUE
        )
        
        task.celery_task_id = celery_task.id
        task.mark_queued()
        
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'File uploaded and queued for processing'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/tasks')
def get_tasks():
    """Get user's tasks with status"""
    user = get_or_create_user()
    tasks = Task.query.filter_by(user_id=user.id).order_by(Task.created_at.desc()).all()
    
    task_list = []
    for task in tasks:
        task_data = {
            'id': task.id,
            'original_filename': task.original_filename,
            'status': task.status,
            'priority': task.priority,
            'progress': task.progress_percentage,
            'current_step': task.current_step,
            'created_at': task.created_at.isoformat(),
            'execution_time': task.execution_time,
            'queue_time': task.queue_time,
            'error_message': task.error_message
        }
        
        if task.result_filename:
            task_data['download_url'] = f"/download/{task.id}"
        
        task_list.append(task_data)
    
    return jsonify(task_list)

@app.route('/task/<task_id>/status')
def get_task_status(task_id):
    """Get detailed status of a specific task"""
    user = get_or_create_user()
    task = Task.query.filter_by(id=task_id, user_id=user.id).first()
    
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    # Get Celery task status if available
    celery_status = None
    if task.celery_task_id:
        from tasks import run_comsol_simulation
        celery_task = run_comsol_simulation.AsyncResult(task.celery_task_id)
        celery_status = {
            'state': celery_task.state,
            'info': celery_task.info
        }
    
    return jsonify({
        'id': task.id,
        'status': task.status,
        'progress': task.progress_percentage,
        'current_step': task.current_step,
        'celery_status': celery_status,
        'error_message': task.error_message,
        'execution_time': task.execution_time
    })

@app.route('/download/<task_id>')
def download_result(task_id):
    """Download result file"""
    user = get_or_create_user()
    task = Task.query.filter_by(id=task_id, user_id=user.id).first()
    
    if not task or not task.result_filename:
        return jsonify({'error': 'Result file not found'}), 404
    
    result_path = Config.RESULTS_FOLDER / task.result_filename
    if not result_path.exists():
        return jsonify({'error': 'Result file not found on disk'}), 404
    
    return send_file(result_path, as_attachment=True, download_name=f"solved_{task.original_filename}")

@app.route('/history')
def history():
    """User task history page"""
    user = get_or_create_user()
    tasks = Task.query.filter_by(user_id=user.id).order_by(Task.created_at.desc()).all()
    return render_template('history.html', tasks=tasks)

@app.route('/queue')
def queue_status():
    """Global queue status page"""
    pending_tasks = Task.query.filter_by(status='pending').order_by(Task.created_at).all()
    running_tasks = Task.query.filter_by(status='running').order_by(Task.started_at).all()
    
    # Get latest system stats
    latest_stats = SystemStats.query.order_by(SystemStats.timestamp.desc()).first()
    
    return render_template('queue.html', 
                         pending_tasks=pending_tasks, 
                         running_tasks=running_tasks,
                         stats=latest_stats)

@app.route('/api/stats')
def api_stats():
    """API endpoint for system statistics"""
    stats = SystemStats.query.order_by(SystemStats.timestamp.desc()).first()
    
    if not stats:
        return jsonify({
            'pending_tasks': 0,
            'running_tasks': 0,
            'completed_today': 0,
            'failed_today': 0
        })
    
    return jsonify({
        'pending_tasks': stats.pending_tasks,
        'running_tasks': stats.running_tasks,
        'completed_today': stats.completed_tasks_today,
        'failed_today': stats.failed_tasks_today,
        'cpu_usage': stats.cpu_usage,
        'memory_usage': stats.memory_usage,
        'disk_usage': stats.disk_usage,
        'avg_queue_time': stats.avg_queue_time,
        'avg_execution_time': stats.avg_execution_time,
        'timestamp': stats.timestamp.isoformat()
    })

@app.route('/logs/<task_id>')
def view_logs(task_id):
    """View task logs"""
    user = get_or_create_user()
    task = Task.query.filter_by(id=task_id, user_id=user.id).first()
    
    if not task or not task.log_filename:
        return jsonify({'error': 'Log file not found'}), 404
    
    log_path = Config.LOGS_FOLDER / task.log_filename
    if not log_path.exists():
        return jsonify({'error': 'Log file not found on disk'}), 404
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            log_content = f.read()
        return jsonify({'logs': log_content})
    except Exception as e:
        return jsonify({'error': f'Failed to read log file: {str(e)}'}), 500

@app.route('/task/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """Cancel a running or queued task"""
    user = get_or_create_user()
    task = Task.query.filter_by(id=task_id, user_id=user.id).first()
    
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    if not task.can_be_cancelled():
        return jsonify({'error': f'Task cannot be cancelled (status: {task.status})'}), 400
    
    try:
        # Cancel Celery task if it exists
        if task.celery_task_id:
            from tasks import run_comsol_simulation
            celery_task = run_comsol_simulation.AsyncResult(task.celery_task_id)
            celery_task.revoke(terminate=True)
        
        # Mark task as cancelled in database
        task.mark_cancelled()
        
        return jsonify({
            'success': True,
            'message': 'Task cancelled successfully'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to cancel task: {str(e)}'}), 500

@app.route('/task/<task_id>/delete', methods=['DELETE'])
def delete_task(task_id):
    """Delete a task and its associated files"""
    user = get_or_create_user()
    task = Task.query.filter_by(id=task_id, user_id=user.id).first()
    
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    try:
        # Cancel task if it's still running
        if task.can_be_cancelled() and task.celery_task_id:
            from tasks import run_comsol_simulation
            celery_task = run_comsol_simulation.AsyncResult(task.celery_task_id)
            celery_task.revoke(terminate=True)
        
        # Clean up associated files
        task.cleanup_files()
        
        # Delete task from database
        db.session.delete(task)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Task deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete task: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)