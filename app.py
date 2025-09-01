import os
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, request, render_template, jsonify, send_file, session, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, Task, SystemStats
from forms import LoginForm, RegistrationForm
from config import Config
# Import moved to avoid circular import

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    Config.init_app(app)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = '请先登录以访问此页面。'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)
    
    # Create database tables
    with app.app_context():
        db.create_all()
        create_admin_user()
    
    return app

def create_admin_user():
    """Create default admin user if it doesn't exist"""
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', is_admin=True)
        admin.set_password('admin123')  # Default password - should be changed
        db.session.add(admin)
        db.session.commit()
        
        # Create admin directories
        user_folder = admin.get_user_folder()
        folder_mapping = {
            'uploads': Config.UPLOAD_FOLDER,
            'results': Config.RESULTS_FOLDER,
            'logs': Config.LOGS_FOLDER
        }
        for folder_type, base_folder in folder_mapping.items():
            folder_path = base_folder / user_folder
            folder_path.mkdir(parents=True, exist_ok=True)
        
        print("Admin user created: username='admin', password='admin123'")

def admin_required(f):
    """Decorator to require admin privileges"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_administrator():
            flash('需要管理员权限才能访问此页面。')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

app = create_app()

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            user.last_seen = datetime.utcnow()
            db.session.commit()
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        flash('用户名或密码错误')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        # Create user-specific directories
        user_folder = user.get_user_folder()
        folder_mapping = {
            'uploads': Config.UPLOAD_FOLDER,
            'results': Config.RESULTS_FOLDER,
            'logs': Config.LOGS_FOLDER
        }
        for folder_type, base_folder in folder_mapping.items():
            folder_path = base_folder / user_folder
            folder_path.mkdir(parents=True, exist_ok=True)
        
        flash('注册成功！请登录。')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    users = User.query.all()
    total_tasks = Task.query.count()
    active_tasks = Task.query.filter(Task.status.in_(['pending', 'queued', 'running'])).count()
    return render_template('admin/dashboard.html', users=users, total_tasks=total_tasks, active_tasks=active_tasks)

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    """Admin user management"""
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/<user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def admin_toggle_user(user_id):
    """Toggle user active status"""
    user = User.query.get_or_404(user_id)
    if user.username == 'admin':
        flash('无法禁用管理员账户')
        return redirect(url_for('admin_users'))
    
    if user.is_active:
        user.deactivate()
        flash(f'用户 {user.username} 已被禁用')
    else:
        user.activate()
        flash(f'用户 {user.username} 已被启用')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    """Delete user and all associated data"""
    user = User.query.get_or_404(user_id)
    if user.username == 'admin':
        flash('无法删除管理员账户')
        return redirect(url_for('admin_users'))
    
    try:
        # Delete all user tasks (will cascade delete files)
        for task in user.tasks:
            task.cleanup_files()
        
        # Delete user directories
        user_folder = user.get_user_folder()
        import shutil
        for folder_type, base_folder in [('uploads', Config.UPLOAD_FOLDER), 
                                       ('results', Config.RESULTS_FOLDER), 
                                       ('logs', Config.LOGS_FOLDER)]:
            folder_path = base_folder / user_folder
            if folder_path.exists():
                shutil.rmtree(folder_path, ignore_errors=True)
        
        # Delete user from database
        db.session.delete(user)
        db.session.commit()
        flash(f'用户 {user.username} 及其所有数据已被删除')
    except Exception as e:
        db.session.rollback()
        flash(f'删除用户失败: {str(e)}')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/tasks')
@login_required
@admin_required
def admin_tasks():
    """Admin task management"""
    tasks = Task.query.order_by(Task.created_at.desc()).all()
    return render_template('admin/tasks.html', tasks=tasks)


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
@login_required
def index():
    """Main page - file upload and task monitoring"""
    recent_tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).limit(10).all()
    return render_template('index.html', tasks=recent_tasks)

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    """Handle file upload and queue simulation task"""
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
        
        # Save uploaded file to user-specific folder
        user_folder = current_user.get_user_folder()
        user_upload_path = Config.UPLOAD_FOLDER / user_folder
        user_upload_path.mkdir(parents=True, exist_ok=True)
        upload_path = user_upload_path / unique_filename
        file.save(upload_path)
        
        # Get priority from form
        priority = request.form.get('priority', 'normal')
        
        # Create task record
        task = Task(
            user_id=current_user.id,
            original_filename=original_filename,
            unique_filename=unique_filename,
            file_size=upload_path.stat().st_size,
            priority=priority
        )
        db.session.add(task)
        db.session.commit()
        
        # Queue Celery task
        result_filename = f"{Path(unique_filename).stem}_solved.mph"
        user_results_path = Config.RESULTS_FOLDER / user_folder
        user_results_path.mkdir(parents=True, exist_ok=True)
        result_path = user_results_path / result_filename
        
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
@login_required
def get_tasks():
    """Get user's tasks with status"""
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).all()
    
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
@login_required
def get_task_status(task_id):
    """Get detailed status of a specific task"""
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    
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
@login_required
def download_result(task_id):
    """Download result file"""
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    
    if not task or not task.result_filename:
        return jsonify({'error': 'Result file not found'}), 404
    
    user_folder = current_user.get_user_folder()
    result_path = Config.RESULTS_FOLDER / user_folder / task.result_filename
    if not result_path.exists():
        return jsonify({'error': 'Result file not found on disk'}), 404
    
    return send_file(result_path, as_attachment=True, download_name=f"solved_{task.original_filename}")

@app.route('/history')
@login_required
def history():
    """User task history page"""
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).all()
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
@login_required
def view_logs(task_id):
    """View task logs"""
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    
    if not task or not task.log_filename:
        return jsonify({'error': 'Log file not found'}), 404
    
    user_folder = current_user.get_user_folder()
    log_path = Config.LOGS_FOLDER / user_folder / task.log_filename
    if not log_path.exists():
        return jsonify({'error': 'Log file not found on disk'}), 404
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            log_content = f.read()
        return jsonify({'logs': log_content})
    except Exception as e:
        return jsonify({'error': f'Failed to read log file: {str(e)}'}), 500

@app.route('/task/<task_id>/cancel', methods=['POST'])
@login_required
def cancel_task(task_id):
    """Cancel a running or queued task"""
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    
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
@login_required
def delete_task(task_id):
    """Delete a task and its associated files"""
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    
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