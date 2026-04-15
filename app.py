import os
import hashlib
import uuid
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc)
from pathlib import Path
from flask import Flask, request, render_template, jsonify, send_file, session, redirect, url_for, flash, g
from urllib.parse import urlparse
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import unicodedata
from models import db, User, Task, SystemStats, ServerConfig, Node
from forms import LoginForm, RegistrationForm, ChangePasswordForm
from config import Config
# Import moved to avoid circular import

def _localtime(dt, fmt='%Y-%m-%d %H:%M'):
    """Convert a UTC datetime (aware or naive) to server local time and format it."""
    if dt is None:
        return '—'
    try:
        import calendar
        if dt.tzinfo is not None:
            ts = dt.timestamp()
        else:
            # Naive datetime stored as UTC → convert to Unix timestamp
            ts = calendar.timegm(dt.timetuple())
        return datetime.fromtimestamp(ts).strftime(fmt)
    except Exception:
        return str(dt)

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Ensure proper encoding for Chinese characters
    app.config['JSON_AS_ASCII'] = False
    
    # Register local-time filter for templates
    app.jinja_env.filters['localtime'] = _localtime

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
        admin = User(username='admin', is_admin=True, must_change_password=True)
        admin.set_password('admin123')
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

        print("Admin user created. Please log in and change the default password immediately.")

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
    return session.get('language', 'en')

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
    referrer = request.referrer
    if referrer and urlparse(referrer).netloc == '':
        return redirect(referrer)
    return redirect(url_for('index'))

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
            user.last_seen = utcnow()
            db.session.commit()
            if user.must_change_password:
                flash('首次登录请修改默认密码。')
                return redirect(url_for('change_password'))
            next_page = request.args.get('next')
            if next_page and urlparse(next_page).netloc == '':
                return redirect(next_page)
            return redirect(url_for('index'))
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
    nodes = Node.query.order_by(Node.registered_at).all()
    online_nodes = sum(1 for n in nodes if n.status in ('online', 'busy'))
    return render_template('admin/dashboard.html', users=users, total_tasks=total_tasks,
                           active_tasks=active_tasks, nodes=nodes, online_nodes=online_nodes)

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
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
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
        
        # Prepare result path, then dispatch to a node or local Celery worker
        result_filename = f"{Path(unique_filename).stem}_solved.mph"
        user_results_path = Config.RESULTS_FOLDER / user_folder
        user_results_path.mkdir(parents=True, exist_ok=True)
        result_path = user_results_path / result_filename

        dispatch_info = _dispatch_task(task, upload_path, result_path)

        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'File uploaded and queued for processing',
            'dispatch': dispatch_info,
        })
        
    except Exception as e:
        db.session.rollback()
        # Clean up the uploaded file if it was saved
        if 'upload_path' in locals() and upload_path.exists():
            try:
                upload_path.unlink()
            except:
                pass
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

        if task.assigned_node_id:
            n = Node.query.get(task.assigned_node_id)
            task_data['node'] = {'hostname': n.hostname, 'ip_address': n.ip_address,
                                 'status': n.status} if n else None
            task_data['result_upload_pending'] = bool(task.result_upload_pending)

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
    
    node_info = None
    if task.assigned_node_id:
        n = Node.query.get(task.assigned_node_id)
        if n:
            node_info = {'hostname': n.hostname, 'ip_address': n.ip_address,
                         'status': n.status}

    return jsonify({
        'id': task.id,
        'status': task.status,
        'progress': task.progress_percentage,
        'current_step': task.current_step,
        'celery_status': celery_status,
        'error_message': task.error_message,
        'execution_time': task.execution_time,
        'node': node_info,
        'result_upload_pending': bool(task.result_upload_pending),
    })

@app.route('/download/<task_id>')
@login_required
def download_result(task_id):
    """Download result file"""
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    # If file is missing but the task ran on a node, queue a re-upload request
    if not task.result_filename and task.assigned_node_id:
        node = Node.query.get(task.assigned_node_id)
        if node:
            stem = Path(task.unique_filename).stem
            action_id = str(uuid.uuid4())
            node.add_pending_action({
                'id': action_id,
                'type': 'reupload',
                'task_id': task.id,
                'output_filename': f"{stem}_solved.mph",
            })
            task.result_upload_pending = True
            db.session.commit()
            return jsonify({
                'error': 'Result file not yet on server',
                'retry': True,
                'message': ('Result file is being fetched from the node computer. '
                            'Please try again in a moment.'),
            }), 202
        return jsonify({'error': 'Result file not available'}), 404

    if not task.result_filename:
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
@login_required
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
            self.timestamp = datetime.now(timezone.utc)
    
    stats = RealTimeStats()
    
    return render_template('queue.html', 
                         pending_tasks=pending_tasks, 
                         running_tasks=running_tasks,
                         stats=stats)

@app.route('/api/stats')
@login_required
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
        'timestamp': datetime.now(timezone.utc).isoformat()
    })

@app.route('/logs/<task_id>')
@login_required
def view_logs(task_id):
    """View task logs"""
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first()
    
    # Node tasks without a saved log file — show status-appropriate message
    if task and task.assigned_node_id and not task.log_filename:
        if task.status in ('queued', 'pending'):
            return jsonify({'logs': '[Task is queued and waiting to run on a node computer]'})
        if task.status == 'running':
            return jsonify({'logs': '[Task is currently running on node computer — logs will be available after completion]'})
        if task.error_log:
            return jsonify({'logs': task.error_log})
        return jsonify({'logs': '[No log was uploaded for this task]'})

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
        # Revoke the Celery reservation so the task won't start if it hasn't yet.
        # Do NOT use terminate=True — on Windows that sends os.kill() which requires
        # admin rights and crashes the worker.  The COMSOL process is killed below
        # via psutil, which is sufficient.
        if task.celery_task_id:
            from tasks import run_comsol_simulation, process_next_queued_task, kill_comsol_process
            celery_task = run_comsol_simulation.AsyncResult(task.celery_task_id)
            celery_task.revoke(terminate=False)
        
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

        # Tell the node to delete its local copy of the result file
        _push_node_delete_action(task)

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
        was_active = task.can_be_cancelled()

        # Revoke Celery reservation (no terminate=True — crashes worker on Windows)
        if task.celery_task_id:
            from tasks import run_comsol_simulation
            celery_task = run_comsol_simulation.AsyncResult(task.celery_task_id)
            celery_task.revoke(terminate=False)

        # Kill the COMSOL OS process and all its children
        if task.process_id:
            try:
                import psutil
                parent = psutil.Process(task.process_id)
                for child in parent.children(recursive=True):
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                try:
                    parent.kill()
                except psutil.NoSuchProcess:
                    pass
            except Exception as e:
                print(f"Warning: Failed to kill COMSOL process {task.process_id}: {e}")

        # Tell the node to delete its local copy of the result file
        _push_node_delete_action(task)

        # Clean up server-side files
        task.cleanup_files()

        # Delete task from database
        db.session.delete(task)
        db.session.commit()
        
        if was_active:
            from tasks import process_next_queued_task
            process_next_queued_task.apply_async(countdown=3)
        
        return jsonify({
            'success': True,
            'message': 'Task deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete task: {str(e)}'}), 500

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_settings():
    """Admin: COMSOL path and CPU core settings"""
    import multiprocessing
    total_cores = multiprocessing.cpu_count()

    if request.method == 'POST':
        for version in Config.COMSOL_VERSIONS:
            path_key = f'comsol_path_{version}'
            path_val = request.form.get(path_key, '').strip()
            if path_val:
                ServerConfig.set(path_key, path_val)

        cores = request.form.get('cpu_cores', '').strip()
        if cores.isdigit() and 1 <= int(cores) <= total_cores:
            ServerConfig.set('cpu_cores', cores)

        flash('Settings saved successfully.' if g.language == 'en' else '设置已保存。', 'success')
        return redirect(url_for('admin_settings'))

    # Build current effective paths from DB or config defaults
    comsol_paths = {}
    for version, info in Config.COMSOL_VERSIONS.items():
        db_path = ServerConfig.get(f'comsol_path_{version}')
        comsol_paths[version] = db_path if db_path else info['executable']

    cpu_cores = int(ServerConfig.get('cpu_cores', total_cores))

    return render_template('admin/settings.html',
                           comsol_versions=Config.COMSOL_VERSIONS,
                           comsol_paths=comsol_paths,
                           cpu_cores=cpu_cores,
                           total_cores=total_cores)

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change user password"""
    form = ChangePasswordForm(current_user)
    
    if form.validate_on_submit():
        try:
            # Update password
            current_user.set_password(form.new_password.data)
            current_user.must_change_password = False
            db.session.commit()

            flash('密码修改成功！', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'密码修改失败: {str(e)}', 'error')
    
    return render_template('change_password.html', form=form)

# ---------------------------------------------------------------------------
# Node distribution API
# ---------------------------------------------------------------------------

def _push_node_delete_action(task):
    """Queue a delete_file action on the node that owns this task's result.
    Safe to call even when the node is offline — the action persists until
    the node comes back online and acknowledges it."""
    if not task.assigned_node_id:
        return
    node = Node.query.get(task.assigned_node_id)
    if not node:
        return
    stem = Path(task.unique_filename).stem
    node.add_pending_action({
        'id': str(uuid.uuid4()),
        'type': 'delete_file',
        'filename': f"{stem}_solved.mph",
    })
    db.session.commit()


def _save_node_log(task, log_text: str):
    """Write node task output to a log file on the server and set task.log_filename.
    Best-effort — logs errors but never raises."""
    try:
        user_folder  = task.user.get_user_folder()
        log_dir      = Config.LOGS_FOLDER / user_folder
        log_dir.mkdir(parents=True, exist_ok=True)
        stem         = Path(task.unique_filename).stem
        log_filename = f"{stem}.log"
        log_path     = log_dir / log_filename
        with open(log_path, 'w', encoding='utf-8', errors='replace') as fh:
            fh.write(log_text)
        task.log_filename = log_filename
    except Exception as exc:
        app.logger.error('_save_node_log failed for task %s: %s', task.id, exc)


def _node_from_request():
    """Authenticate a node from X-Node-Id / X-Node-Token headers.
    Returns the Node object or None."""
    node_id    = request.headers.get('X-Node-Id')
    node_token = request.headers.get('X-Node-Token')
    if not node_id or not node_token:
        return None
    return Node.query.filter_by(id=node_id, auth_token=node_token).first()


@app.route('/api/nodes/register', methods=['POST'])
def node_register():
    """Node calls this on startup to register itself."""
    data = request.get_json(silent=True) or {}
    hostname         = data.get('hostname', 'unknown')
    ip_address       = data.get('ip_address') or request.remote_addr
    comsol_versions  = data.get('comsol_versions', [])
    cpu_cores        = int(data.get('cpu_cores', 1))
    cpu_model        = data.get('cpu_model') or None

    # Re-register by hostname+ip if already known so nodes survive restarts.
    node = Node.query.filter_by(hostname=hostname, ip_address=ip_address).first()
    if node:
        node.comsol_versions = comsol_versions
        node.cpu_cores       = cpu_cores
        if cpu_model:
            node.cpu_model   = cpu_model
        node.status          = 'online'
        node.touch()
    else:
        import secrets
        node = Node(
            hostname=hostname,
            ip_address=ip_address,
            auth_token=secrets.token_hex(32),
            cpu_cores=cpu_cores,
            cpu_model=cpu_model,
        )
        node.comsol_versions = comsol_versions
        db.session.add(node)

    db.session.commit()
    # Assign any waiting tasks to this newly-online node
    _dispatch_pending_node_tasks()
    return jsonify({'node_id': node.id, 'auth_token': node.auth_token}), 200


@app.route('/api/nodes/heartbeat', methods=['POST'])
def node_heartbeat():
    """Node sends this every ~15 s to stay alive."""
    node = _node_from_request()
    if not node:
        return jsonify({'error': 'Unauthorized'}), 401

    data        = request.get_json(silent=True) or {}
    new_status  = data.get('status', 'online')   # 'online' | 'busy' | 'offline'
    prev_status = node.status
    if new_status in ('online', 'busy', 'offline'):
        node.status = new_status
    disk_free = data.get('disk_free_gb')
    if disk_free is not None:
        node.disk_free_gb = float(disk_free)
    node.touch()
    if new_status == 'offline':
        node.current_task_id = None
    actions = node.pending_actions   # snapshot before commit
    db.session.commit()

    if new_status == 'offline' and prev_status != 'offline':
        # Node just went offline — immediately re-pend its tasks
        _repend_tasks_for_offline_nodes([node.id])
    elif prev_status == 'offline' and new_status == 'online':
        # Node came back online — dispatch waiting tasks to it
        _dispatch_pending_node_tasks()

    return jsonify({'ok': True, 'pending_actions': actions}), 200


@app.route('/api/nodes/task/poll', methods=['GET'])
def node_task_poll():
    """Node polls for a task assigned to it."""
    node = _node_from_request()
    if not node:
        return jsonify({'error': 'Unauthorized'}), 401

    node.touch()
    db.session.commit()

    # 1. Check for a task already assigned to this node
    task = Task.query.filter_by(
        assigned_node_id=node.id,
        status='queued'
    ).order_by(Task.created_at).first()

    # 2. If none, try to claim an unassigned queued task (pull model)
    if not task and node.status != 'busy':
        for ver in node.comsol_versions:
            candidate = Task.query.filter_by(
                assigned_node_id=None,
                status='queued',
                comsol_version=ver,
            ).order_by(Task.created_at).first()
            if candidate:
                candidate.assigned_node_id = node.id
                db.session.commit()
                task = candidate
                break

    pending_actions = node.pending_actions

    if not task:
        return jsonify({'task': None, 'pending_actions': pending_actions}), 200

    return jsonify({
        'task': {
            'id': task.id,
            'comsol_version': task.comsol_version,
            'cpu_cores': int(ServerConfig.get('cpu_cores', node.cpu_cores)),
            'input_file_url': f"/api/nodes/task/{task.id}/file",
            'unique_filename': task.unique_filename,
        },
        'pending_actions': pending_actions,
    }), 200


@app.route('/api/nodes/task/<task_id>/file', methods=['GET'])
def node_download_task_file(task_id):
    """Node downloads the input .mph file for a task."""
    node = _node_from_request()
    if not node:
        return jsonify({'error': 'Unauthorized'}), 401

    task = Task.query.filter_by(id=task_id, assigned_node_id=node.id).first()
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    user_folder = task.user.get_user_folder()
    file_path   = Config.UPLOAD_FOLDER / user_folder / task.unique_filename
    if not file_path.exists():
        return jsonify({'error': 'Input file not found'}), 404

    # Stream with 4 MB chunks to avoid Werkzeug's 8 KB default block size,
    # which causes Nagle+delayed-ACK stalls on Windows LAN (~200 ms per chunk).
    file_size = file_path.stat().st_size
    CHUNK = 4 * 1024 * 1024

    def _stream():
        with open(file_path, 'rb') as fh:
            while True:
                data = fh.read(CHUNK)
                if not data:
                    break
                yield data

    from flask import Response as _Response
    return _Response(
        _stream(),
        headers={
            'Content-Disposition': f'attachment; filename="{task.unique_filename}"',
            'Content-Length':      str(file_size),
            'Content-Type':        'application/octet-stream',
        }
    )


@app.route('/api/nodes/task/<task_id>/start', methods=['POST'])
def node_task_start(task_id):
    """Node reports it has started executing a task."""
    node = _node_from_request()
    if not node:
        return jsonify({'error': 'Unauthorized'}), 401

    task = Task.query.filter_by(id=task_id, assigned_node_id=node.id).first()
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    data = request.get_json(silent=True) or {}
    task.mark_started()
    task.process_id = data.get('process_id')
    node.status = 'busy'
    node.current_task_id = task_id
    db.session.commit()
    return jsonify({'ok': True}), 200


@app.route('/api/nodes/task/<task_id>/progress', methods=['POST'])
def node_task_progress(task_id):
    """Node streams progress updates for a running task."""
    node = _node_from_request()
    if not node:
        return jsonify({'error': 'Unauthorized'}), 401

    task = Task.query.filter_by(id=task_id, assigned_node_id=node.id).first()
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    # If the task was cancelled while the node was running it, tell the node to abort
    if task.status == 'cancelled':
        return jsonify({'ok': True, 'cancel': True}), 200

    data       = request.get_json(silent=True) or {}
    percentage = float(data.get('percentage', task.progress_percentage or 0))
    step       = data.get('step')
    task.update_progress(percentage, step)
    return jsonify({'ok': True, 'cancel': False}), 200


@app.route('/api/nodes/task/<task_id>/complete', methods=['POST'])
def node_task_complete(task_id):
    """Node marks a task completed and optionally uploads the result file.

    The status update and the file upload are intentionally decoupled:
    mark_completed() is called as soon as the request is authenticated so
    the task status is always updated even if the file save fails.
    """
    node = _node_from_request()
    if not node:
        return jsonify({'error': 'Unauthorized'}), 401

    task = Task.query.filter_by(id=task_id, assigned_node_id=node.id).first()
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    # ── 1. Mark the task complete immediately ─────────────────────────────
    result_filename = None
    stem = Path(task.unique_filename).stem
    expected_result = f"{stem}_solved.mph"

    # ── 2. Try to save the result file (best-effort, never blocks status) ──
    if 'result_file' in request.files:
        result_file = request.files['result_file']
        try:
            user_folder = task.user.get_user_folder()
            result_dir  = Config.RESULTS_FOLDER / user_folder
            result_dir.mkdir(parents=True, exist_ok=True)
            result_path = result_dir / expected_result
            result_file.save(str(result_path))
            result_filename = expected_result
        except Exception as exc:
            app.logger.error('node_task_complete: could not save result file '
                             'for task %s: %s', task_id, exc)

    # ── 3. Save log text if the node included it ──────────────────────────
    log_text = (request.get_json(silent=True) or {}).get('log_text')
    if log_text:
        _save_node_log(task, log_text)

    task.mark_completed(result_filename)   # commits status = 'completed'
    node.status          = 'online'
    node.current_task_id = None

    # If the file landed on the server, tell the node it can delete its copy
    if result_filename:
        node.add_pending_action({
            'id': str(uuid.uuid4()),
            'type': 'delete_file',
            'filename': result_filename,
        })

    db.session.commit()

    try:
        from tasks import update_system_stats
        update_system_stats.delay()
    except Exception:
        pass

    _dispatch_pending_node_tasks()
    return jsonify({'ok': True, 'has_result': result_filename is not None}), 200


@app.route('/api/nodes/task/<task_id>/upload_result', methods=['POST'])
def node_upload_result(task_id):
    """Node uploads the result file for an already-completed task.

    Called by the node client as a follow-up if the first /complete call
    succeeded without a file (e.g., the file was too large for a single
    multipart request).
    """
    node = _node_from_request()
    if not node:
        return jsonify({'error': 'Unauthorized'}), 401

    task = Task.query.filter_by(id=task_id, assigned_node_id=node.id).first()
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    if 'result_file' not in request.files:
        return jsonify({'error': 'No result_file in request'}), 400

    result_file = request.files['result_file']
    try:
        user_folder     = task.user.get_user_folder()
        result_dir      = Config.RESULTS_FOLDER / user_folder
        result_dir.mkdir(parents=True, exist_ok=True)
        stem            = Path(task.unique_filename).stem
        result_filename = f"{stem}_solved.mph"
        result_path     = result_dir / result_filename
        result_file.save(str(result_path))
        task.result_filename      = result_filename
        task.result_upload_pending = False
        # File is now on the server — tell the node to delete its copy
        node.add_pending_action({
            'id': str(uuid.uuid4()),
            'type': 'delete_file',
            'filename': result_filename,
        })
        db.session.commit()
    except Exception as exc:
        app.logger.error('node_upload_result: save failed for task %s: %s',
                         task_id, exc)
        return jsonify({'error': str(exc)}), 500

    return jsonify({'ok': True}), 200


@app.route('/api/nodes/task/<task_id>/fail', methods=['POST'])
def node_task_fail(task_id):
    """Node reports that a task has failed."""
    node = _node_from_request()
    if not node:
        return jsonify({'error': 'Unauthorized'}), 401

    task = Task.query.filter_by(id=task_id, assigned_node_id=node.id).first()
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    data          = request.get_json(silent=True) or {}
    error_message = data.get('error_message', 'Node reported failure')
    error_log     = data.get('error_log', '')
    log_text      = data.get('log_text') or error_log
    if log_text:
        _save_node_log(task, log_text)
    task.mark_failed(error_message, error_log)   # commits status = 'failed'
    node.status          = 'online'
    node.current_task_id = None
    db.session.commit()

    try:
        from tasks import update_system_stats
        update_system_stats.delay()
    except Exception:
        pass

    _dispatch_pending_node_tasks()
    return jsonify({'ok': True}), 200


@app.route('/api/nodes/task/<task_id>/upload_log', methods=['POST'])
def node_upload_log(task_id):
    """Node uploads (partial) log text for any terminal task state.

    Called after abort/cancel so partial output is preserved even when the
    normal complete/fail path is skipped.  Safe to call for completed, failed,
    and cancelled tasks alike.
    """
    node = _node_from_request()
    if not node:
        return jsonify({'error': 'Unauthorized'}), 401

    # Accept any task still assigned to this node regardless of status
    task = Task.query.filter_by(id=task_id, assigned_node_id=node.id).first()
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    data     = request.get_json(silent=True) or {}
    log_text = data.get('log_text', '')
    if log_text:
        _save_node_log(task, log_text)
        db.session.commit()

    return jsonify({'ok': True}), 200


@app.route('/api/nodes/actions/done', methods=['POST'])
def node_actions_done():
    """Node reports which pending actions it has completed.
    Body: {"completed": ["action_id1", "action_id2", ...]}
    """
    node = _node_from_request()
    if not node:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    completed_ids = data.get('completed', [])
    if completed_ids:
        node.remove_pending_actions(completed_ids)
        db.session.commit()
    return jsonify({'ok': True}), 200


@app.route('/api/nodes/list')
@login_required
@admin_required
def admin_nodes_list():
    """Admin API: current node status."""
    nodes = Node.query.order_by(Node.registered_at).all()
    return jsonify([n.to_dict() for n in nodes]), 200


@app.route('/admin/nodes')
@login_required
@admin_required
def admin_nodes():
    """Admin: node management page."""
    nodes = Node.query.order_by(Node.registered_at).all()
    return render_template('admin/nodes.html', nodes=nodes)


@app.route('/admin/nodes/<node_id>/remove', methods=['POST'])
@login_required
@admin_required
def admin_remove_node(node_id):
    """Admin: remove a node registration."""
    node = Node.query.get_or_404(node_id)
    db.session.delete(node)
    db.session.commit()
    flash('Node removed.' if g.language == 'en' else '节点已移除。')
    return redirect(url_for('admin_nodes'))


# ---------------------------------------------------------------------------
# Node-aware task dispatcher — replaces the direct Celery call in upload_file
# ---------------------------------------------------------------------------

def _dispatch_pending_node_tasks():
    """Assign unallocated pending/queued tasks to an online node, or fall back
    to the local Celery worker if no suitable node is available."""
    waiting = Task.query.filter(
        Task.status.in_(['pending', 'queued']),
        Task.assigned_node_id.is_(None),
    ).order_by(Task.created_at).all()

    if not waiting:
        return

    online_nodes = Node.query.filter_by(status='online').all()

    for task in waiting:
        # --- Try to assign to an online node first ---
        assigned = False
        for node in online_nodes:
            if task.comsol_version in node.comsol_versions:
                if task.celery_task_id:
                    try:
                        from tasks import run_comsol_simulation
                        run_comsol_simulation.AsyncResult(
                            task.celery_task_id).revoke()
                        task.celery_task_id = None
                    except Exception:
                        pass
                task.assigned_node_id = node.id
                if task.status != 'queued':
                    task.mark_queued()
                else:
                    db.session.commit()
                assigned = True
                break

        if assigned:
            continue

        # --- Fall back to local Celery worker ---
        # Only start locally if no local task is already running.
        local_running = Task.query.filter_by(
            status='running', assigned_node_id=None
        ).count()
        if local_running > 0:
            continue

        upload_path = (Config.UPLOAD_FOLDER
                       / task.user.get_user_folder()
                       / task.unique_filename)
        result_name = Path(task.unique_filename).stem + '_solved.mph'
        result_path = (Config.RESULTS_FOLDER
                       / task.user.get_user_folder()
                       / result_name)
        result_path.parent.mkdir(parents=True, exist_ok=True)

        if task.celery_task_id:
            # Already queued in Celery — don't double-submit
            continue

        from tasks import run_comsol_simulation
        celery_task = run_comsol_simulation.apply_async(
            args=[task.id, str(upload_path), str(result_path)],
            queue=Config.HIGH_PRIORITY_QUEUE if task.priority == 'high'
                  else Config.NORMAL_PRIORITY_QUEUE,
        )
        task.celery_task_id = celery_task.id
        task.mark_queued()
        # Only one local task at a time — stop after dispatching one
        break


def _dispatch_task(task, upload_path, result_path):
    """Assign task to an online node that supports the required COMSOL version,
    falling back to the local Celery worker if none are available."""
    comsol_ver = task.comsol_version

    # Find an idle node that supports this COMSOL version
    candidates = Node.query.filter_by(status='online').all()
    chosen = None
    for node in candidates:
        if comsol_ver in node.comsol_versions:
            chosen = node
            break

    if chosen:
        # Assign to node — it will poll and pick it up
        task.assigned_node_id = chosen.id
        task.mark_queued()
        # No Celery task needed; node polls /api/nodes/task/poll
        return {'mode': 'node', 'node_id': chosen.id, 'node_hostname': chosen.hostname}
    else:
        # Fall back to local Celery worker
        from tasks import run_comsol_simulation
        celery_task = run_comsol_simulation.apply_async(
            args=[task.id, str(upload_path), str(result_path)],
            queue=Config.HIGH_PRIORITY_QUEUE if task.priority == 'high'
                  else Config.NORMAL_PRIORITY_QUEUE
        )
        task.celery_task_id = celery_task.id
        task.mark_queued()
        return {'mode': 'local', 'celery_task_id': celery_task.id}


# ---------------------------------------------------------------------------
def _repend_tasks_for_offline_nodes(node_ids: list):
    """Re-pend any running/queued tasks whose assigned node just went offline,
    then try to dispatch them to remaining online nodes."""
    if not node_ids:
        return
    orphaned = Task.query.filter(
        Task.status.in_(['queued', 'running']),
        Task.assigned_node_id.in_(node_ids),
    ).all()
    for stuck in orphaned:
        stuck.assigned_node_id = None
        stuck.status = 'pending'
        stuck.started_at = None
    if orphaned:
        db.session.commit()
    _dispatch_pending_node_tasks()


# Heartbeat monitor — background thread, started once when Flask starts
# ---------------------------------------------------------------------------

def _start_heartbeat_monitor(flask_app):
    """Background thread: mark nodes offline if last_seen > 60 s ago."""
    import threading
    from datetime import timedelta, datetime as _datetime

    def _monitor():
        while True:
            import time
            time.sleep(30)
            try:
                with flask_app.app_context():
                    # Use naive UTC so the comparison works with SQLite's
                    # naive-datetime storage (timezone-aware datetimes produce
                    # strings with +00:00 that compare incorrectly against
                    # the plain YYYY-MM-DD HH:MM:SS values stored on disk).
                    cutoff = _datetime.utcnow() - timedelta(seconds=60)
                    stale = Node.query.filter(
                        Node.status != 'offline',
                        Node.last_seen < cutoff
                    ).all()
                    for node in stale:
                        node.status = 'offline'
                        node.current_task_id = None

                    if stale:
                        stale_ids = [n.id for n in stale]
                        db.session.commit()
                        _repend_tasks_for_offline_nodes(stale_ids)
            except Exception as exc:
                # Never crash the monitor thread
                pass

    t = threading.Thread(target=_monitor, name='heartbeat-monitor', daemon=True)
    t.start()


# Start monitor after first request context is available.
# We use a flag so it only fires once even in debug reload mode.
_monitor_started = False

@app.before_request
def _ensure_monitor_running():
    global _monitor_started
    if not _monitor_started:
        _monitor_started = True
        _start_heartbeat_monitor(app)


if __name__ == '__main__':
    import os as _os
    debug = _os.environ.get('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes')
    app.run(debug=debug, host='0.0.0.0', port=5000)