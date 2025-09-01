// JavaScript for COMSOL Simulation Management System

// Global variables
let uploadForm = null;
let tasksRefreshInterval = null;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        initializeUploadForm();
    }
    
    // Initialize auto-refresh if on index page
    if (document.getElementById('tasksContainer')) {
        startAutoRefresh();
        // Initial load of tasks to ensure buttons are visible immediately
        refreshTasks();
    }
    
    // Apply progress bar widths from data attributes
    applyProgressBarWidths();
});

// Apply width to progress bars from data-width attribute
function applyProgressBarWidths() {
    const progressBars = document.querySelectorAll('.progress-bar[data-width]');
    progressBars.forEach(bar => {
        const width = bar.getAttribute('data-width');
        if (width) {
            bar.style.width = `${width}%`;
        }
    });
}

// Upload form initialization
function initializeUploadForm() {
    uploadForm.addEventListener('submit', handleFileUpload);
    
    // Drag and drop functionality
    const fileInput = document.getElementById('fileInput');
    
    uploadForm.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadForm.classList.add('dragover');
    });
    
    uploadForm.addEventListener('dragleave', function(e) {
        e.preventDefault();
        uploadForm.classList.remove('dragover');
    });
    
    uploadForm.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadForm.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            updateFileInputDisplay();
        }
    });
    
    fileInput.addEventListener('change', updateFileInputDisplay);
}

// Update file input display
function updateFileInputDisplay() {
    const fileInput = document.getElementById('fileInput');
    const fileName = fileInput.files[0]?.name;
    
    if (fileName) {
        // Update label or add visual feedback
        const label = document.querySelector('label[for="fileInput"]');
        label.textContent = `已选择: ${fileName}`;
        label.classList.add('text-success');
    }
}

// Handle file upload
async function handleFileUpload(e) {
    e.preventDefault();
    
    const formData = new FormData(uploadForm);
    const submitBtn = uploadForm.querySelector('button[type="submit"]');
    const statusDiv = document.getElementById('uploadStatus');
    
    // Disable submit button and show loading
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>上传中...';
    
    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            statusDiv.innerHTML = `
                <div class="alert alert-success">
                    <i class="fas fa-check-circle me-2"></i>
                    ${result.message}
                </div>
            `;
            
            // Reset form
            uploadForm.reset();
            document.querySelector('label[for="fileInput"]').textContent = '选择 .mph 文件';
            document.querySelector('label[for="fileInput"]').classList.remove('text-success');
            
            // Refresh tasks
            setTimeout(refreshTasks, 1000);
            
        } else {
            throw new Error(result.error || '上传失败');
        }
        
    } catch (error) {
        statusDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>
                ${error.message}
            </div>
        `;
    } finally {
        // Re-enable submit button
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fas fa-upload me-1"></i>上传并开始仿真';
    }
}

// Refresh tasks list
async function refreshTasks() {
    try {
        // Add visual feedback for refresh button
        const refreshBtn = document.querySelector('button[onclick="refreshTasks()"]');
        if (refreshBtn) {
            const originalHTML = refreshBtn.innerHTML;
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 刷新中...';
            refreshBtn.disabled = true;
        }
        
        const response = await fetch('/tasks');
        const tasks = await response.json();
        
        updateTasksTable(tasks);
        
        // Restore refresh button
        if (refreshBtn) {
            refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i> 刷新';
            refreshBtn.disabled = false;
        }
        
        // Show success notification
        showNotification('任务列表已刷新', 'success');
        
    } catch (error) {
        console.error('Failed to refresh tasks:', error);
        
        // Restore refresh button on error
        const refreshBtn = document.querySelector('button[onclick="refreshTasks()"]');
        if (refreshBtn) {
            refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i> 刷新';
            refreshBtn.disabled = false;
        }
        
        showNotification('刷新失败: ' + error.message, 'error');
    }
}

// Update tasks table
function updateTasksTable(tasks) {
    const tasksTable = document.getElementById('tasksTable');
    const tasksContainer = document.getElementById('tasksContainer');
    
    if (!tasksTable || !tasksContainer) return;
    
    if (tasks.length === 0) {
        tasksContainer.innerHTML = `
            <div class="text-center text-muted py-4">
                <i class="fas fa-inbox fa-3x mb-3"></i>
                <p>暂无任务记录</p>
            </div>
        `;
        return;
    }
    
    tasksTable.innerHTML = tasks.map(task => {
        const statusBadge = getStatusBadge(task.status);
        const priorityBadge = getPriorityBadge(task.priority);
        const progressBar = getProgressBar(task.progress, task.status);
        const actions = getTaskActions(task);
        
        return `
            <tr>
                <td>${task.original_filename}</td>
                <td>${statusBadge}</td>
                <td>${priorityBadge}</td>
                <td>${progressBar}</td>
                <td>${formatDateTime(task.created_at)}</td>
                <td>${actions}</td>
            </tr>
        `;
    }).join('');
    
    // Apply width to progress bars after updating DOM
    applyProgressBarWidths();
}

// Get status badge HTML
function getStatusBadge(status) {
    const badges = {
        'pending': 'bg-secondary',
        'queued': 'bg-warning',
        'running': 'bg-primary',
        'completed': 'bg-success',
        'failed': 'bg-danger',
        'cancelled': 'bg-dark'
    };
    
    const statusText = {
        'pending': '待处理',
        'queued': '队列中',
        'running': '运行中',
        'completed': '已完成',
        'failed': '失败',
        'cancelled': '已取消'
    };
    
    return `<span class="badge ${badges[status] || 'bg-secondary'}">${statusText[status] || status}</span>`;
}

// Get priority badge HTML
function getPriorityBadge(priority) {
    const badge = priority === 'high' ? 'bg-danger' : 'bg-primary';
    const text = priority === 'high' ? '高优先级' : '普通';
    return `<span class="badge ${badge}">${text}</span>`;
}

// Get progress bar HTML
function getProgressBar(progress, status) {
    const isActive = status === 'running';
    const barClass = status === 'completed' ? 'bg-success' : 
                    status === 'failed' ? 'bg-danger' : 
                    isActive ? 'progress-bar-striped progress-bar-animated' : '';
    
    return `
        <div class="progress task-progress">
            <div class="progress-bar ${barClass}" role="progressbar" 
                 aria-valuenow="${progress}" aria-valuemin="0" aria-valuemax="100"
                 data-width="${progress}">
                ${progress}%
            </div>
        </div>
    `;
}

// Get task actions HTML
function getTaskActions(task) {
    let actions = '';
    
    if (task.download_url) {
        actions += `
            <a href="${task.download_url}" class="btn btn-sm btn-success me-1">
                <i class="fas fa-download"></i>
            </a>
        `;
    }
    
    // Cancel button for active tasks
    if (task.status === 'pending' || task.status === 'queued' || task.status === 'running') {
        actions += `
            <button class="btn btn-sm btn-warning me-1" onclick="cancelTask('${task.id}')" title="取消任务">
                <i class="fas fa-stop"></i>
            </button>
        `;
    }
    
    actions += `
        <button class="btn btn-sm btn-info me-1" onclick="viewLogs('${task.id}')" title="查看日志">
            <i class="fas fa-file-alt"></i>
        </button>
        <button class="btn btn-sm btn-danger" onclick="deleteTask('${task.id}')" title="删除任务">
            <i class="fas fa-trash"></i>
        </button>
    `;
    
    return actions;
}

// Format datetime string
function formatDateTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// View task logs
async function viewLogs(taskId) {
    try {
        const response = await fetch(`/logs/${taskId}`);
        const result = await response.json();
        
        if (response.ok) {
            document.getElementById('logContent').textContent = result.logs;
            new bootstrap.Modal(document.getElementById('logModal')).show();
        } else {
            alert('无法加载日志: ' + result.error);
        }
        
    } catch (error) {
        alert('加载日志失败: ' + error.message);
    }
}

// Cancel task
async function cancelTask(taskId) {
    if (!confirm('确定要取消这个任务吗？')) {
        return;
    }
    
    try {
        const response = await fetch(`/task/${taskId}/cancel`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showNotification('任务已取消', 'success');
            refreshTasks();
        } else {
            showNotification('取消任务失败: ' + result.error, 'error');
        }
        
    } catch (error) {
        showNotification('取消任务失败: ' + error.message, 'error');
    }
}

// Delete task
async function deleteTask(taskId) {
    if (!confirm('确定要删除这个任务吗？此操作将删除所有相关文件且无法恢复。')) {
        return;
    }
    
    try {
        const response = await fetch(`/task/${taskId}/delete`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showNotification('任务已删除', 'success');
            refreshTasks();
        } else {
            showNotification('删除任务失败: ' + result.error, 'error');
        }
        
    } catch (error) {
        showNotification('删除任务失败: ' + error.message, 'error');
    }
}

// Update system statistics
async function updateSystemStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        
        // Update stat numbers
        const elements = {
            'pendingTasks': stats.pending_tasks,
            'runningTasks': stats.running_tasks,
            'completedToday': stats.completed_today,
            'failedToday': stats.failed_today
        };
        
        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value || 0;
            }
        });
        
    } catch (error) {
        console.error('Failed to update system stats:', error);
    }
}

// Start auto-refresh for tasks and stats
function startAutoRefresh() {
    // Refresh tasks every 10 seconds
    tasksRefreshInterval = setInterval(refreshTasks, 10000);
    
    // Update stats every 5 seconds
    setInterval(updateSystemStats, 5000);
    
    // Initial load
    updateSystemStats();
}

// Stop auto-refresh (useful when navigating away)
function stopAutoRefresh() {
    if (tasksRefreshInterval) {
        clearInterval(tasksRefreshInterval);
        tasksRefreshInterval = null;
    }
}

// Utility function to show notifications
function showNotification(message, type = 'info') {
    const alertClass = {
        'success': 'alert-success',
        'error': 'alert-danger',
        'warning': 'alert-warning',
        'info': 'alert-info'
    };
    
    const notification = document.createElement('div');
    notification.className = `alert ${alertClass[type]} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// Handle page visibility change to pause/resume auto-refresh
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        stopAutoRefresh();
    } else if (document.getElementById('tasksContainer')) {
        startAutoRefresh();
    }
});
