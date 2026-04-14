// COMSOL Simulation Management System — frontend logic

let tasksRefreshInterval = null;
let statsRefreshInterval  = null;

document.addEventListener('DOMContentLoaded', function () {
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        initUploadForm(uploadForm);
    }
    if (document.getElementById('tasksContainer')) {
        startAutoRefresh();
        refreshTasks();
    }
    applyProgressBars();
});

// ─── Progress bars ────────────────────────────────────────────────────────────

function applyProgressBars() {
    document.querySelectorAll('progress.task-progress-bar').forEach(applyProgressColor);
    document.querySelectorAll('progress.resource-progress-bar').forEach(applyResourceColor);
}

function applyProgressColor(el) {
    // colours driven by data-status attribute
    const status = el.dataset.status || '';
    el.classList.remove('p-success', 'p-danger', 'p-warning', 'p-running');
    if (status === 'completed') el.classList.add('p-success');
    else if (status === 'failed')  el.classList.add('p-danger');
    else if (status === 'running') el.classList.add('p-running');
}

function applyResourceColor(el) {
    const level = el.dataset.level || 'ok';
    el.classList.remove('p-ok', 'p-med', 'p-high');
    el.classList.add('p-' + level);
}

// ─── Upload form ──────────────────────────────────────────────────────────────

function initUploadForm(form) {
    form.addEventListener('submit', handleFileUpload);

    const fileInput = document.getElementById('fileInput');
    const dropZone  = document.getElementById('dropZone');

    if (dropZone) {
        dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('dragover'); });
        dropZone.addEventListener('dragleave', e => { e.preventDefault(); dropZone.classList.remove('dragover'); });
        dropZone.addEventListener('drop', e => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                fileInput.files = e.dataTransfer.files;
                updateFileLabel(fileInput.files[0].name);
            }
        });
    }

    if (fileInput) {
        fileInput.addEventListener('change', () => {
            if (fileInput.files[0]) updateFileLabel(fileInput.files[0].name);
        });
    }
}

function updateFileLabel(name) {
    const label = document.querySelector('label[for="fileInput"]');
    if (label) {
        label.textContent = name;
        label.style.color = 'var(--c-green)';
    }
}

async function handleFileUpload(e) {
    e.preventDefault();
    const form      = e.currentTarget;
    const submitBtn = form.querySelector('button[type="submit"]');
    const statusDiv = document.getElementById('uploadStatus');

    submitBtn.disabled = true;
    const origHTML = submitBtn.innerHTML;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> uploading…';

    try {
        const response = await fetch('/upload', { method: 'POST', body: new FormData(form) });
        const result   = await response.json();

        if (response.ok) {
            statusDiv.innerHTML = `<div class="alert alert-success">${result.message}</div>`;
            form.reset();
            const label = document.querySelector('label[for="fileInput"]');
            if (label) { label.style.color = ''; label.textContent = label.dataset.default || ''; }
            setTimeout(() => refreshTasks(true), 900);
        } else {
            throw new Error(result.error || 'Upload failed');
        }
    } catch (err) {
        statusDiv.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = origHTML;
    }
}

// ─── Task list ────────────────────────────────────────────────────────────────

async function refreshTasks(silent = false) {
    const refreshBtn = document.querySelector('button[onclick="refreshTasks()"]');
    if (refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    }
    try {
        const resp  = await fetch('/tasks');
        const tasks = await resp.json();
        updateTasksTable(tasks);
        if (!silent) showToast('info', 'Refreshed');
    } catch (err) {
        console.error('refresh failed', err);
    } finally {
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = '<i class="fas fa-arrows-rotate"></i>';
        }
    }
}

function updateTasksTable(tasks) {
    const tbody     = document.getElementById('tasksTable');
    const container = document.getElementById('tasksContainer');
    if (!container) return;

    if (!tasks.length) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-inbox d-block"></i>
                <h6>No tasks yet</h6>
                <p>Upload a .mph file to get started.</p>
            </div>`;
        return;
    }

    // If the table doesn't exist yet (was showing empty state), rebuild it
    if (!tbody) {
        container.innerHTML = `
            <div class="table-responsive">
                <table class="table table-hover">
                    <thead><tr>
                        <th>File</th><th>Status</th><th>Priority</th>
                        <th style="min-width:110px;">Progress</th>
                        <th>Created</th><th>Actions</th>
                    </tr></thead>
                    <tbody id="tasksTable"></tbody>
                </table>
            </div>`;
    }

    const tb = document.getElementById('tasksTable');
    if (!tb) return;

    tb.innerHTML = tasks.map(task => `
        <tr>
            <td style="font-weight:500;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                ${escHtml(task.original_filename)}
            </td>
            <td>${statusBadge(task.status)}</td>
            <td>${priorityBadge(task.priority)}</td>
            <td>
                <progress class="task-progress-bar p-${progressClass(task.status)}"
                          value="${task.progress}"
                          max="100"
                          data-status="${task.status}"></progress>
                <div style="font-size:11px;color:var(--c-text-muted);margin-top:3px;">${task.progress}%</div>
            </td>
            <td style="color:var(--c-text-sec);white-space:nowrap;">${formatDate(task.created_at)}</td>
            <td>${taskActions(task)}</td>
        </tr>`).join('');
}

function progressClass(status) {
    if (status === 'completed') return 'success';
    if (status === 'failed')    return 'danger';
    if (status === 'running')   return 'running';
    return 'default';
}

function statusBadge(status) {
    const map = {
        pending:   ['bg-secondary', '待处理'],
        queued:    ['bg-info',      '队列中'],
        running:   ['bg-warning',   '运行中'],
        completed: ['bg-success',   '已完成'],
        failed:    ['bg-danger',    '失败'],
        cancelled: ['bg-dark',      '已取消'],
    };
    const [cls, label] = map[status] || ['bg-secondary', status];
    return `<span class="badge ${cls}">${label}</span>`;
}

function priorityBadge(priority) {
    return priority === 'high'
        ? `<span class="badge bg-danger">高优先级</span>`
        : `<span class="badge bg-secondary">普通</span>`;
}

function taskActions(task) {
    let html = '';
    if (task.download_url) {
        html += `<a href="${escHtml(task.download_url)}" class="btn btn-success btn-sm" title="下载"><i class="fas fa-download"></i></a> `;
    }
    if (['pending','queued','running'].includes(task.status)) {
        html += `<button class="btn btn-warning btn-sm" onclick="cancelTask('${task.id}')" title="取消"><i class="fas fa-stop"></i></button> `;
    }
    html += `<button class="btn btn-secondary btn-sm" onclick="viewLogs('${task.id}')" title="日志"><i class="fas fa-file-lines"></i></button> `;
    html += `<button class="btn btn-danger btn-sm" onclick="deleteTask('${task.id}')" title="删除"><i class="fas fa-trash"></i></button>`;
    return `<div style="display:flex;gap:6px;flex-wrap:wrap;">${html}</div>`;
}

function formatDate(str) {
    if (!str) return '—';
    return new Date(str).toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit'
    });
}

function escHtml(s) {
    return String(s)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ─── Task actions ─────────────────────────────────────────────────────────────

async function viewLogs(taskId) {
    try {
        const resp   = await fetch(`/logs/${taskId}`);
        const result = await resp.json();
        if (resp.ok) {
            document.getElementById('logContent').textContent = result.logs;
            new bootstrap.Modal(document.getElementById('logModal')).show();
        } else {
            showToast('error', '无法加载日志: ' + result.error);
        }
    } catch (err) {
        showToast('error', '加载日志失败: ' + err.message);
    }
}

async function cancelTask(taskId) {
    if (!confirm('确定要取消这个任务吗？')) return;
    try {
        const resp   = await fetch(`/task/${taskId}/cancel`, { method: 'POST' });
        const result = await resp.json();
        if (resp.ok) { showToast('success', '任务已取消'); refreshTasks(); }
        else          showToast('error', '取消失败: ' + result.error);
    } catch (err) {
        showToast('error', '取消失败: ' + err.message);
    }
}

async function deleteTask(taskId) {
    if (!confirm('确定要删除这个任务吗？此操作将删除所有相关文件且无法恢复。')) return;
    try {
        const resp   = await fetch(`/task/${taskId}/delete`, { method: 'DELETE' });
        const result = await resp.json();
        if (resp.ok) { showToast('success', '任务已删除'); refreshTasks(); }
        else          showToast('error', '删除失败: ' + result.error);
    } catch (err) {
        showToast('error', '删除失败: ' + err.message);
    }
}

// ─── System stats ─────────────────────────────────────────────────────────────

async function updateSystemStats() {
    try {
        const resp  = await fetch('/api/stats');
        if (!resp.ok) return;
        const stats = await resp.json();
        const map = {
            pendingTasks:   stats.pending_tasks,
            runningTasks:   stats.running_tasks,
            completedToday: stats.completed_today,
            failedToday:    stats.failed_today,
        };
        Object.entries(map).forEach(([id, val]) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val ?? 0;
        });
    } catch (_) { /* silent — stats are non-critical */ }
}

// ─── Auto-refresh ─────────────────────────────────────────────────────────────

function startAutoRefresh() {
    clearInterval(tasksRefreshInterval);
    clearInterval(statsRefreshInterval);
    tasksRefreshInterval = setInterval(() => refreshTasks(true), 10000);
    statsRefreshInterval  = setInterval(updateSystemStats, 5000);
    updateSystemStats();
}

function stopAutoRefresh() {
    clearInterval(tasksRefreshInterval);
    tasksRefreshInterval = null;
    clearInterval(statsRefreshInterval);
    statsRefreshInterval = null;
}

document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopAutoRefresh();
    } else if (document.getElementById('tasksContainer')) {
        startAutoRefresh();
    }
});

// ─── Toast notifications ──────────────────────────────────────────────────────

function showToast(type, message) {
    const toast = document.createElement('div');
    toast.className = `n-toast ${type}`;
    toast.innerHTML = `<span class="n-dot"></span><span>${escHtml(message)}</span>`;
    document.body.appendChild(toast);

    // Stack toasts vertically
    const existing = document.querySelectorAll('.n-toast');
    let offset = 70;
    existing.forEach(t => { if (t !== toast) offset += t.offsetHeight + 8; });
    toast.style.top = offset + 'px';

    setTimeout(() => {
        toast.style.transition = 'opacity 0.2s';
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 220);
    }, 3500);
}

// Legacy alias used by base template (flash messages auto-dismiss)
function showNotification(message, type = 'info') {
    showToast(type === 'error' ? 'error' : type, message);
}
