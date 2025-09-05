import os
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, request, render_template, jsonify, send_file, session, redirect, url_for, flash, g
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import unicodedata
from models import db, User, Task, SystemStats
from forms import LoginForm, RegistrationForm, ChangePasswordForm
from config import Config
# Import moved to avoid circular import

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Ensure proper encoding for Chinese characters
    app.config['JSON_AS_ASCII'] = False
    
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

# Language translations
TRANSLATIONS = {
    'zh': {
        # Navigation
        'title': 'COMSOL® 仿真管理系统',
        'home': '首页',
        'history': '历史记录',
        'queue_status': '队列状态',
        'admin': '管理',
        'dashboard': '控制台',
        'user_management': '用户管理',
        'task_management': '任务管理',
        'change_password': '修改密码',
        'logout': '退出',
        'login': '登录',
        'register': '注册',
        'administrator': '管理员',
        'language': '语言',
        'chinese': '中文',
        'english': 'English',
        'version': '版本',
        
        # Main page content
        'upload_simulation_file': '上传仿真文件',
        'select_mph_file': '选择 .mph 文件',
        'only_mph_format': '仅支持 COMSOL® .mph 格式文件',
        'task_priority': '任务优先级',
        'normal_priority': '普通优先级',
        'high_priority': '高优先级',
        'upload_and_start': '上传并开始仿真',
        'system_status': '系统状态',
        'pending': '等待中',
        'running': '运行中',
        'completed_today': '今日完成',
        'failed_today': '今日失败',
        'my_tasks': '我的任务',
        'refresh': '刷新',
        'no_tasks': '暂无任务记录',
        'task_logs': '任务日志',
        
        # Table headers
        'filename': '文件名',
        'status': '状态',
        'priority': '优先级',
        'progress': '进度',
        'created_time': '创建时间',
        'actions': '操作',
        
        # Status labels
        'completed': '已完成',
        'failed': '失败',
        'cancelled': '已取消',
        'queued': '队列中',
        'pending_status': '待处理',
        'normal': '普通',
        'high': '高优先级',
        
        # Action buttons
        'download': '下载',
        'logs': '日志',
        'cancel': '取消',
        'delete': '删除',
        'cancel_task': '取消任务',
        'delete_task': '删除任务',
        
        # Login page
        'user_login': '用户登录',
        'username': '用户名',
        'password': '密码',
        'login_button': '登录',
        'no_account': '还没有账户？',
        'register_now': '立即注册',
        
        # History page
        'task_history': '任务历史记录',
        'completion_time': '完成时间',
        'execution_time': '执行时长',
        'no_history': '暂无历史记录',
        'no_tasks_submitted': '您还没有提交过任何仿真任务',
        'upload_first_file': '上传第一个文件',
        'error_info': '错误信息',
        
        # Queue Status page
        'task_queue': '任务队列',
        'waiting_queue': '等待队列',
        'running_queue': '运行中',
        'queue_empty': '队列为空',
        'no_running_tasks': '无运行任务',
        'system_statistics': '系统统计',
        'cpu_usage': 'CPU 使用率',
        'memory_usage': '内存使用率',
        'disk_usage': '磁盘使用率',
        'avg_queue_time': '平均排队时间',
        'avg_execution_time': '平均执行时间',
        'update_time': '更新时间',
        'realtime_data': '实时数据',
        'no_statistics': '暂无统计数据',
        'start_time': '开始时间',
        'unknown_time': '未知时间',
        
        # Registration page
        'user_registration': '用户注册',
        'username_length': '用户名长度为3-20个字符',
        'password_length': '密码至少6个字符',
        'have_account': '已有账户？',
        'login_now': '立即登录',
        'confirm_password': '确认密码',
        
        # Admin pages
        'admin_dashboard': '管理控制台',
        'total_users': '总用户数',
        'total_tasks': '总任务数',
        'active_tasks': '活跃任务',
        'active_users': '活跃用户',
        'system_load': '系统负载',
        'recent_activities': '最近活动',
        'user_registered': '用户注册',
        'task_submitted': '任务提交',
        'task_completed': '任务完成',
        'view_all': '查看全部',
        'recent_registered_users': '最近注册用户',
        'registration_time': '注册时间',
        'active': '活跃',
        'disabled': '禁用',
        'quick_actions': '快速操作',
        'manage_users': '管理用户',
        'manage_tasks': '管理任务',
        'view_queue': '查看队列',
        'all_users': '所有用户',
        'total_users_count': '共',
        'users_count': '个用户',
        'role': '角色',
        'last_login': '最后登录',
        'task_count': '任务数',
        'all_tasks': '所有任务',
        'total_tasks_count': '共',
        'tasks_count': '个任务',
        'task_id': '任务ID',
        'user': '用户',
        'actions': '操作',
        'created_time': '创建时间',
        'execution_time': '执行时间',
        'normal_priority': '普通',
        'refresh': '刷新',
        'task_status_statistics': '任务状态统计',
        'system_information': '系统信息',
        'in_progress': '进行中',
        'total_task_count': '总任务数',
        'average_execution_time': '平均执行时间',
        'no_data': '暂无数据',
        'normal_user': '普通用户',
        'never_logged_in': '从未登录',
        'disable_user': '禁用',
        'enable_user': '启用',
        'delete_user': '删除',
        'system_admin': '系统管理员',
        'confirm_disable_user': '确定要禁用用户',
        'confirm_delete_user': '确定要删除用户',
        'delete_warning': '及其所有数据吗？此操作不可恢复！',
        
        # File input
        'choose_file': '选择文件',
        'no_file_chosen': '未选择文件',
        
        # Change password page
        'current_password': '当前密码',
        'new_password': '新密码',
        'confirm_new_password': '确认新密码',
        'change_password_title': '修改密码',
        'password_changed_success': '密码修改成功',
        
        # Form labels from forms.py
        'username_label': '用户名',
        'password_label': '密码',
        'confirm_password_label': '确认密码',
        'login_submit': '登录',
        'register_submit': '注册',
        'change_password_submit': '修改密码',
        'username_exists': '用户名已存在，请选择其他用户名。',
        'password_mismatch': '两次输入的密码不一致',
        'current_password_incorrect': '当前密码不正确。',
        
        # Common
        'submit': '提交',
        'close': '关闭',
        'save': '保存',
        'cancel_action': '取消'
    },
    'en': {
        # Navigation
        'title': 'COMSOL® Simulation Management System',
        'home': 'Home',
        'history': 'History',
        'queue_status': 'Queue Status',
        'admin': 'Admin',
        'dashboard': 'Dashboard',
        'user_management': 'User Management',
        'task_management': 'Task Management',
        'change_password': 'Change Password',
        'logout': 'Logout',
        'login': 'Login',
        'register': 'Register',
        'administrator': 'Admin',
        'language': 'Language',
        'chinese': '中文',
        'english': 'English',
        'version': 'Version',
        
        # Main page content
        'upload_simulation_file': 'Upload Simulation File',
        'select_mph_file': 'Select .mph File',
        'only_mph_format': 'Only COMSOL® .mph format files supported',
        'task_priority': 'Task Priority',
        'normal_priority': 'Normal Priority',
        'high_priority': 'High Priority',
        'upload_and_start': 'Upload and Start Simulation',
        'system_status': 'System Status',
        'pending': 'Pending',
        'running': 'Running',
        'completed_today': 'Completed Today',
        'failed_today': 'Failed Today',
        'my_tasks': 'My Tasks',
        'refresh': 'Refresh',
        'no_tasks': 'No task records',
        'task_logs': 'Task Logs',
        
        # Table headers
        'filename': 'Filename',
        'status': 'Status',
        'priority': 'Priority',
        'progress': 'Progress',
        'created_time': 'Created Time',
        'actions': 'Actions',
        
        # Status labels
        'completed': 'Completed',
        'failed': 'Failed',
        'cancelled': 'Cancelled',
        'queued': 'Queued',
        'pending_status': 'Pending',
        'normal': 'Normal',
        'high': 'High Priority',
        
        # Action buttons
        'download': 'Download',
        'logs': 'Logs',
        'cancel': 'Cancel',
        'delete': 'Delete',
        'cancel_task': 'Cancel Task',
        'delete_task': 'Delete Task',
        
        # Login page
        'user_login': 'User Login',
        'username': 'Username',
        'password': 'Password',
        'login_button': 'Login',
        'no_account': "Don't have an account?",
        'register_now': 'Register Now',
        
        # History page
        'task_history': 'Task History',
        'completion_time': 'Completion Time',
        'execution_time': 'Execution Time',
        'no_history': 'No History Records',
        'no_tasks_submitted': 'You have not submitted any simulation tasks yet',
        'upload_first_file': 'Upload First File',
        'error_info': 'Error Information',
        
        # Queue Status page
        'task_queue': 'Task Queue',
        'waiting_queue': 'Waiting Queue',
        'running_queue': 'Running',
        'queue_empty': 'Queue is Empty',
        'no_running_tasks': 'No Running Tasks',
        'system_statistics': 'System Statistics',
        'cpu_usage': 'CPU Usage',
        'memory_usage': 'Memory Usage',
        'disk_usage': 'Disk Usage',
        'avg_queue_time': 'Average Queue Time',
        'avg_execution_time': 'Average Execution Time',
        'update_time': 'Update Time',
        'realtime_data': 'Real-time Data',
        'no_statistics': 'No Statistics Available',
        'start_time': 'Start Time',
        'unknown_time': 'Unknown Time',
        
        # Registration page
        'user_registration': 'User Registration',
        'username_length': 'Username length: 3-20 characters',
        'password_length': 'Password minimum 6 characters',
        'have_account': 'Already have an account?',
        'login_now': 'Login Now',
        'confirm_password': 'Confirm Password',
        
        # Admin pages
        'admin_dashboard': 'Admin Dashboard',
        'total_users': 'Total Users',
        'total_tasks': 'Total Tasks',
        'active_tasks': 'Active Tasks',
        'active_users': 'Active Users',
        'system_load': 'System Load',
        'recent_activities': 'Recent Activities',
        'user_registered': 'User Registered',
        'task_submitted': 'Task Submitted',
        'task_completed': 'Task Completed',
        'view_all': 'View All',
        'recent_registered_users': 'Recent Registered Users',
        'registration_time': 'Registration Time',
        'active': 'Active',
        'disabled': 'Disabled',
        'quick_actions': 'Quick Actions',
        'manage_users': 'Manage Users',
        'manage_tasks': 'Manage Tasks',
        'view_queue': 'View Queue',
        
        # File input
        'choose_file': 'Choose File',
        'no_file_chosen': 'No File Chosen',
        
        # Change password page
        'current_password': 'Current Password',
        'new_password': 'New Password',
        'confirm_new_password': 'Confirm New Password',
        'change_password_title': 'Change Password',
        'password_changed_success': 'Password changed successfully',
        
        # Form labels from forms.py
        'username_label': 'Username',
        'password_label': 'Password',
        'confirm_password_label': 'Confirm Password',
        'login_submit': 'Login',
        'register_submit': 'Register',
        'change_password_submit': 'Change Password',
        'username_exists': 'Username already exists, please choose another.',
        'password_mismatch': 'Passwords do not match',
        'current_password_incorrect': 'Current password is incorrect.',
        
        # Admin users page
        'all_users': 'All Users',
        'total_users_count': 'Total Users',
        'role': 'Role',
        'last_login': 'Last Login',
        'task_count': 'Task Count',
        
        # Admin tasks page
        'all_tasks': 'All Tasks',
        'total_tasks_count': 'Total',
        'tasks_count': 'Tasks',
        'task_id': 'Task ID',
        'user': 'User',
        'actions': 'Actions',
        'created_time': 'Created Time',
        'execution_time': 'Execution Time',
        'normal_priority': 'Normal',
        'refresh': 'Refresh',
        'task_status_statistics': 'Task Status Statistics',
        'system_information': 'System Information',
        'in_progress': 'In Progress',
        'total_task_count': 'Total Tasks',
        'average_execution_time': 'Average Execution Time',
        'no_data': 'No Data',
        'normal_user': 'Normal User',
        'never_logged_in': 'Never Logged In',
        'disable_user': 'Disable',
        'enable_user': 'Enable',
        'delete_user': 'Delete',
        'system_admin': 'System Administrator',
        'confirm_disable_user': 'Are you sure you want to disable user',
        'confirm_delete_user': 'Are you sure you want to delete user',
        'delete_warning': 'and all their data? This action cannot be undone!',
        
        # Common
        'submit': 'Submit',
        'close': 'Close',
        'save': 'Save',
        'cancel_action': 'Cancel'
    }
}

def get_language():
    """Get current language from session or default to Chinese"""
    return session.get('language', 'zh')

def get_text(key):
    """Get translated text for current language"""
    lang = get_language()
    return TRANSLATIONS.get(lang, TRANSLATIONS['zh']).get(key, key)

@app.before_request
def before_request():
    """Set up language context before each request"""
    g.language = get_language()
    g.get_text = get_text
    g.config = Config

@app.route('/set_language/<language>')
def set_language(language):
    """Set language preference"""
    if language in ['zh', 'en']:
        session['language'] = language
    return redirect(request.referrer or url_for('index'))

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

def secure_chinese_filename(filename):
    """Secure filename while preserving Chinese characters"""
    if not filename:
        return ''
    
    # Keep the original filename but remove dangerous characters
    # Allow Chinese characters, alphanumeric, dots, hyphens, underscores
    import re
    # Remove path separators and other dangerous characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Remove control characters
    filename = ''.join(char for char in filename if ord(char) >= 32)
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext
    
    return filename.strip()

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
        # Generate unique filename with Chinese character support
        original_filename = secure_chinese_filename(file.filename)
        unique_filename = generate_unique_filename(original_filename)
        
        # Save uploaded file to user-specific folder
        user_folder = current_user.get_user_folder()
        user_upload_path = Config.UPLOAD_FOLDER / user_folder
        user_upload_path.mkdir(parents=True, exist_ok=True)
        upload_path = user_upload_path / unique_filename
        file.save(upload_path)
        
        # Get priority and COMSOL version from form
        priority = request.form.get('priority', 'normal')
        comsol_version = request.form.get('comsol_version', Config.DEFAULT_COMSOL_VERSION)
        
        # Validate COMSOL version
        if comsol_version not in Config.COMSOL_VERSIONS:
            return jsonify({'error': 'Invalid COMSOL version selected'}), 400
        
        # Create task record
        task = Task(
            user_id=current_user.id,
            original_filename=original_filename,
            unique_filename=unique_filename,
            file_size=upload_path.stat().st_size,
            priority=priority,
            comsol_version=comsol_version
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
            'comsol_version': task.comsol_version,
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
    
    # Ensure proper encoding for Chinese characters in download filename
    download_filename = f"solved_{task.original_filename}"
    return send_file(result_path, as_attachment=True, download_name=download_filename)

@app.route('/history')
@login_required
def history():
    """User task history page"""
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).all()
    return render_template('history.html', tasks=tasks)

@app.route('/queue')
def queue_status():
    """Global queue status page"""
    from datetime import date
    
    pending_tasks = Task.query.filter(Task.status.in_(['pending', 'queued'])).order_by(Task.created_at).all()
    running_tasks = Task.query.filter_by(status='running').order_by(Task.started_at).all()
    
    # Calculate real-time statistics
    today = date.today()
    completed_today = Task.query.filter(
        Task.status == 'completed',
        db.func.date(Task.completed_at) == today
    ).count()
    
    failed_today = Task.query.filter(
        Task.status == 'failed',
        db.func.date(Task.completed_at) == today
    ).count()
    
    # Create a stats object with real-time data
    class RealTimeStats:
        def __init__(self):
            self.pending_tasks = len(pending_tasks)
            self.running_tasks = len(running_tasks)
            self.completed_tasks_today = completed_today
            self.failed_tasks_today = failed_today
            
            # Get real-time system resource usage
            try:
                import psutil
                self.cpu_usage = psutil.cpu_percent(interval=1)
                self.memory_usage = psutil.virtual_memory().percent
                # Use C:\ for Windows, / for Unix
                disk_path = 'C:\\' if os.name == 'nt' else '/'
                self.disk_usage = psutil.disk_usage(disk_path).percent
            except ImportError:
                # Fallback if psutil is not available
                self.cpu_usage = 0
                self.memory_usage = 0
                self.disk_usage = 0
            
            # Calculate average times from recent tasks
            recent_tasks = Task.query.filter(
                Task.completed_at >= today,
                Task.execution_time.isnot(None)
            ).all()
            
            # Safe average calculations
            self.avg_queue_time = 0
            self.avg_execution_time = 0
            
            if recent_tasks:
                # Filter out None values for queue_time
                valid_queue_times = [t.queue_time for t in recent_tasks if t.queue_time is not None]
                if valid_queue_times:
                    self.avg_queue_time = sum(valid_queue_times) / len(valid_queue_times)
                
                # Filter out None values for execution_time
                valid_exec_times = [t.execution_time for t in recent_tasks if t.execution_time is not None]
                if valid_exec_times:
                    self.avg_execution_time = sum(valid_exec_times) / len(valid_exec_times)
            self.timestamp = datetime.now()
    
    stats = RealTimeStats()
    
    return render_template('queue.html', 
                         pending_tasks=pending_tasks, 
                         running_tasks=running_tasks,
                         stats=stats)

@app.route('/api/stats')
def api_stats():
    """API endpoint for system statistics"""
    from datetime import date
    
    # Calculate real-time statistics
    pending_tasks = Task.query.filter(Task.status.in_(['pending', 'queued'])).count()
    running_tasks = Task.query.filter_by(status='running').count()
    
    # Get today's completed/failed tasks
    today = date.today()
    completed_today = Task.query.filter(
        Task.status == 'completed',
        db.func.date(Task.completed_at) == today
    ).count()
    
    failed_today = Task.query.filter(
        Task.status == 'failed',
        db.func.date(Task.completed_at) == today
    ).count()
    
    # Get real-time system resource usage
    try:
        import psutil
        cpu_usage = psutil.cpu_percent(interval=1)
        memory_usage = psutil.virtual_memory().percent
        disk_path = 'C:\\' if os.name == 'nt' else '/'
        disk_usage = psutil.disk_usage(disk_path).percent
    except ImportError:
        cpu_usage = 0
        memory_usage = 0
        disk_usage = 0
    
    # Calculate average times
    recent_tasks = Task.query.filter(
        Task.completed_at >= today,
        Task.execution_time.isnot(None)
    ).all()
    
    # Safe average calculations
    avg_queue_time = 0
    avg_execution_time = 0
    
    if recent_tasks:
        # Filter out None values for queue_time
        valid_queue_times = [t.queue_time for t in recent_tasks if t.queue_time is not None]
        if valid_queue_times:
            avg_queue_time = sum(valid_queue_times) / len(valid_queue_times)
        
        # Filter out None values for execution_time
        valid_exec_times = [t.execution_time for t in recent_tasks if t.execution_time is not None]
        if valid_exec_times:
            avg_execution_time = sum(valid_exec_times) / len(valid_exec_times)
    
    return jsonify({
        'pending_tasks': pending_tasks,
        'running_tasks': running_tasks,
        'completed_today': completed_today,
        'failed_today': failed_today,
        'cpu_usage': cpu_usage,
        'memory_usage': memory_usage,
        'disk_usage': disk_usage,
        'avg_queue_time': avg_queue_time,
        'avg_execution_time': avg_execution_time,
        'timestamp': datetime.now().isoformat()
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
        # Try to detect encoding and read log file properly
        import locale
        import chardet
        
        # First try to detect encoding
        with open(log_path, 'rb') as f:
            raw_data = f.read()
            detected = chardet.detect(raw_data)
            encoding = detected.get('encoding', 'utf-8')
        
        # If detection fails or confidence is low, use system encoding
        if not encoding or detected.get('confidence', 0) < 0.7:
            encoding = locale.getpreferredencoding()
        
        # Read with detected/system encoding
        with open(log_path, 'r', encoding=encoding, errors='replace') as f:
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
        # Cancel the Celery task
        if task.celery_task_id:
            from tasks import run_comsol_simulation, process_next_queued_task, kill_comsol_process
            celery_task = run_comsol_simulation.AsyncResult(task.celery_task_id)
            celery_task.revoke(terminate=True)
        
        # Kill the COMSOL process immediately (synchronously)
        if task.process_id:
            try:
                import psutil
                # Kill the process and all its children immediately
                parent = psutil.Process(task.process_id)
                children = parent.children(recursive=True)
                
                # Kill children first
                for child in children:
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                
                # Kill parent process
                try:
                    parent.kill()
                except psutil.NoSuchProcess:
                    pass
                    
            except Exception as e:
                # Log the error but don't fail the cancellation
                print(f"Warning: Failed to kill COMSOL process {task.process_id}: {e}")
        
        # Mark task as cancelled in database
        task.mark_cancelled()
        
        # Start the next queued task after a brief delay
        from tasks import process_next_queued_task
        process_next_queued_task.apply_async(countdown=3)
        
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

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change user password"""
    form = ChangePasswordForm(current_user)
    
    if form.validate_on_submit():
        try:
            # Update password
            current_user.set_password(form.new_password.data)
            db.session.commit()
            
            flash('密码修改成功！', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'密码修改失败: {str(e)}', 'error')
    
    return render_template('change_password.html', form=form)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)