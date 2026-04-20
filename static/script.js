// COMSOL Simulation Management System — frontend logic

let tasksRefreshInterval = null;
let statsRefreshInterval  = null;

const activeUploads = new Map();  // uid -> { xhr, filename, card, rowEl, lastPct }
let _uploadSeq = 0;

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
    if (!label) return;
    label.innerHTML = `<i class="fas fa-folder-open"></i><span> ${escHtml(name)}</span>`;
    label.style.color = 'var(--c-green)';
}

function resetFileLabel() {
    const label = document.querySelector('label[for="fileInput"]');
    if (!label) return;
    const text = label.dataset.default || (isZh() ? '未选择文件' : 'No file chosen');
    label.innerHTML = `<i class="fas fa-folder-open"></i><span> ${escHtml(text)}</span>`;
    label.style.color = '';
}

function handleFileUpload(e) {
    e.preventDefault();
    const form      = e.currentTarget;
    const fileInput = document.getElementById('fileInput');
    if (!fileInput || !fileInput.files[0]) return;

    const filename = fileInput.files[0].name;

    // Snapshot the form data synchronously before resetting
    const formData = new FormData(form);

    // Reset form immediately so the user can queue another upload without waiting
    form.reset();
    resetFileLabel();

    startUpload(formData, filename);
}

function startUpload(formData, filename) {
    const uid = ++_uploadSeq;

    // ── progress card inside the upload form panel ──
    const statusDiv = document.getElementById('uploadStatus');
    let list = document.getElementById('_uploadsList');
    if (!list) {
        statusDiv.innerHTML =
            `<div style="font-size:11px;font-weight:700;color:var(--c-text-muted);text-transform:uppercase;` +
            `letter-spacing:.6px;margin-bottom:8px;">` +
            `<i class="fas fa-arrow-up-from-bracket" style="margin-right:4px;"></i>` +
            `${isZh() ? '正在上传' : 'Uploading'}</div>` +
            `<div id="_uploadsList"></div>`;
        list = document.getElementById('_uploadsList');
    }
    const card = document.createElement('div');
    card.id = `_uc${uid}`;
    card.style.cssText = 'padding:9px 12px;border:1px solid var(--c-border);border-radius:10px;' +
                         'background:var(--c-bg-warm);margin-bottom:6px;';
    card.innerHTML =
        `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:5px;">` +
        `  <span style="font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;" title="${escHtml(filename)}">` +
        `    <i class="fas fa-file-code" style="color:var(--c-blue);font-size:11px;margin-right:4px;"></i>${escHtml(filename)}</span>` +
        `  <span id="_upct${uid}" style="font-size:12px;color:var(--c-text-muted);white-space:nowrap;">0%</span>` +
        `</div>` +
        `<div style="background:var(--c-border);border-radius:3px;height:4px;overflow:hidden;">` +
        `  <div id="_ubar${uid}" style="height:100%;width:0%;background:var(--c-blue);transition:width .12s;"></div>` +
        `</div>`;
    list.appendChild(card);

    // ── phantom row in the tasks table ──
    const rowEl = _injectUploadRow(uid, filename);

    const xhr = new XMLHttpRequest();
    activeUploads.set(uid, { xhr, filename, card, rowEl, lastPct: 0 });

    xhr.upload.addEventListener('progress', e => {
        if (!e.lengthComputable) return;
        _setUploadProgress(uid, Math.round(e.loaded / e.total * 100));
    });

    xhr.addEventListener('load', () => {
        const ct = (xhr.getResponseHeader('Content-Type') || '').toLowerCase();
        const isJson = ct.includes('application/json');

        if (!isJson) {
            // Server returned HTML or text (e.g. 500 error page or 302 redirect)
            const preview = (xhr.responseText || '').substring(0, 50).trim();
            _finishUpload(uid, false, isZh() ? `服务器错误 (${xhr.status}): ${preview}` : `Server error (${xhr.status}): ${preview}`);
            return;
        }

        let result;
        try {
            result = JSON.parse(xhr.responseText);
        } catch (parseErr) {
            _finishUpload(uid, false, isZh() ? '无法解析服务器响应' : 'Invalid server response');
            return;
        }

        if (xhr.status >= 200 && xhr.status < 300 && !result.error) {
            _finishUpload(uid, true, result.message || (isZh() ? '已提交' : 'Pending'));
            setTimeout(() => refreshTasks(true), 800);
        } else {
            _finishUpload(uid, false, result.error || `HTTP ${xhr.status}`);
        }
    });

    xhr.addEventListener('error', () => {
        _finishUpload(uid, false, isZh() ? '网络错误' : 'Network error');
    });

    xhr.open('POST', '/upload');
    xhr.send(formData);
}

function _setUploadProgress(uid, pct) {
    const up = activeUploads.get(uid);
    if (up) up.lastPct = pct;
    const bar   = document.getElementById(`_ubar${uid}`);
    const pctEl = document.getElementById(`_upct${uid}`);
    if (bar)   bar.style.width    = pct + '%';
    if (pctEl) pctEl.textContent  = pct + '%';
    if (up && up.rowEl) {
        const rb = up.rowEl.querySelector('._urbar');
        const rp = up.rowEl.querySelector('._urpct');
        if (rb) rb.style.width   = pct + '%';
        if (rp) rp.textContent   = pct + '%';
    }
}

function _finishUpload(uid, success, message) {
    const up = activeUploads.get(uid);
    activeUploads.delete(uid);

    const card  = document.getElementById(`_uc${uid}`);
    if (card) {
        const bar   = document.getElementById(`_ubar${uid}`);
        const pctEl = document.getElementById(`_upct${uid}`);
        if (bar)   { bar.style.transition = 'none'; bar.style.width = '100%';
                     bar.style.background = success ? 'var(--c-green)' : 'var(--c-red)'; }
        if (pctEl) { 
            // Show the actual message from the server instead of hardcoded 'Failed'
            const displayMsg = success ? `✓ ${message}` : `✗ ${message}`;
            pctEl.textContent = displayMsg;
            pctEl.style.color = success ? 'var(--c-green)' : 'var(--c-red)';
            pctEl.title = displayMsg; // tooltip for long messages
        }
        setTimeout(() => {
            card.style.transition = 'opacity .3s';
            card.style.opacity    = '0';
            setTimeout(() => { card.remove(); _cleanupUploadsPanel(); }, 320);
        }, success ? 2500 : 6000); // keep errors visible longer
    }

    // Remove phantom row — real refresh will replace it with the actual task row
    const rowEl = up ? up.rowEl : null;
    if (rowEl && rowEl.parentNode) rowEl.remove();
}

function _cleanupUploadsPanel() {
    const list = document.getElementById('_uploadsList');
    if (list && list.children.length === 0) {
        const sd = document.getElementById('uploadStatus');
        if (sd) sd.innerHTML = '';
    }
}

function _injectUploadRow(uid, filename) {
    let tb = document.getElementById('tasksTable');
    if (!tb) {
        const container = document.getElementById('tasksContainer');
        if (!container) return null;
        container.innerHTML =
            `<div class="table-responsive"><table class="table table-hover">` +
            `<thead><tr>` +
            `<th>${isZh() ? '文件名' : 'File'}</th><th>${isZh() ? '状态' : 'Status'}</th>` +
            `<th>${isZh() ? '优先级' : 'Priority'}</th>` +
            `<th style="min-width:110px;">${isZh() ? '进度' : 'Progress'}</th>` +
            `<th>${isZh() ? '创建时间' : 'Created'}</th>` +
            `<th>${isZh() ? '操作' : 'Actions'}</th>` +
            `</tr></thead><tbody id="tasksTable"></tbody></table></div>`;
        tb = document.getElementById('tasksTable');
    }
    if (!tb) return null;

    const tr = document.createElement('tr');
    tr.id = `_urow${uid}`;
    tr.innerHTML =
        `<td style="font-weight:500;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escHtml(filename)}">${escHtml(filename)}</td>` +
        `<td><span class="badge bg-info">${isZh() ? '上传中' : 'Uploading'}</span></td>` +
        `<td style="color:var(--c-text-muted);">—</td>` +
        `<td>` +
        `  <div style="background:var(--c-border);border-radius:3px;height:5px;overflow:hidden;margin-bottom:3px;">` +
        `    <div class="_urbar" style="height:100%;width:0%;background:var(--c-blue);transition:width .12s;"></div>` +
        `  </div>` +
        `  <div class="_urpct" style="font-size:11px;color:var(--c-text-muted);">0%</div>` +
        `</td>` +
        `<td style="color:var(--c-text-sec);white-space:nowrap;">${isZh() ? '正在上传…' : 'Uploading…'}</td>` +
        `<td style="color:var(--c-text-muted);">—</td>`;
    tb.insertBefore(tr, tb.firstChild);
    return tr;
}

function _reInjectUploadRows() {
    activeUploads.forEach((up, uid) => {
        if (!document.getElementById(`_urow${uid}`)) {
            const newRow = _injectUploadRow(uid, up.filename);
            up.rowEl = newRow;
            if (newRow && up.lastPct) {
                const rb = newRow.querySelector('._urbar');
                const rp = newRow.querySelector('._urpct');
                if (rb) rb.style.width  = up.lastPct + '%';
                if (rp) rp.textContent  = up.lastPct + '%';
            }
        }
    });
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
                <h6>${isZh() ? '暂无任务记录' : 'No tasks yet'}</h6>
                <p>${isZh() ? '上传 .mph 文件开始仿真' : 'Upload a .mph file to get started.'}</p>
            </div>`;
        return;
    }

    // If the table doesn't exist yet (was showing empty state), rebuild it
    if (!tbody) {
        container.innerHTML = `
            <div class="table-responsive">
                <table class="table table-hover">
                    <thead><tr>
                        <th>${isZh() ? '文件名' : 'File'}</th><th>${isZh() ? '状态' : 'Status'}</th><th>${isZh() ? '优先级' : 'Priority'}</th>
                        <th style="min-width:110px;">${isZh() ? '进度' : 'Progress'}</th>
                        <th>${isZh() ? '创建时间' : 'Created'}</th><th>${isZh() ? '操作' : 'Actions'}</th>
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

    // Re-inject phantom rows for any uploads still in progress
    _reInjectUploadRows();
}

function progressClass(status) {
    if (status === 'completed') return 'success';
    if (status === 'failed')    return 'danger';
    if (status === 'running')   return 'running';
    return 'default';
}

function isZh() {
    return document.documentElement.lang === 'zh-CN';
}

function statusBadge(status) {
    const map = {
        pending:   ['bg-secondary', isZh() ? '待处理' : 'Pending'],
        running:   ['bg-warning',   isZh() ? '运行中' : 'Running'],
        completed: ['bg-success',   isZh() ? '已完成' : 'Completed'],
        failed:    ['bg-danger',    isZh() ? '失败'   : 'Failed'],
        cancelled: ['bg-dark',      isZh() ? '已取消' : 'Cancelled'],
    };
    const [cls, label] = map[status] || ['bg-secondary', status];
    return `<span class="badge ${cls}">${label}</span>`;
}

function priorityBadge(priority) {
    return priority === 'high'
        ? `<span class="badge bg-danger">${isZh() ? '高优先级' : 'High Priority'}</span>`
        : `<span class="badge bg-secondary">${isZh() ? '普通' : 'Normal'}</span>`;
}

function taskActions(task) {
    let html = '';
    if (task.download_url) {
        html += `<a href="${escHtml(task.download_url)}" class="btn btn-success btn-sm" title="${isZh() ? '下载' : 'Download'}"><i class="fas fa-download"></i></a> `;
    }
    if (['pending','running'].includes(task.status)) {
        html += `<button class="btn btn-warning btn-sm" onclick="cancelTask('${task.id}')" title="${isZh() ? '取消' : 'Cancel'}"><i class="fas fa-stop"></i></button> `;
    }
    html += `<button class="btn btn-secondary btn-sm" onclick="viewLogs('${task.id}')" title="${isZh() ? '日志' : 'Logs'}"><i class="fas fa-file-lines"></i></button> `;
    html += `<button class="btn btn-danger btn-sm" onclick="deleteTask('${task.id}')" title="${isZh() ? '删除' : 'Delete'}"><i class="fas fa-trash"></i></button>`;
    return `<div style="display:flex;gap:6px;flex-wrap:wrap;">${html}</div>`;
}

function formatDate(str) {
    if (!str) return '—';
    return new Date(str).toLocaleString(isZh() ? 'zh-CN' : 'en-GB', {
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
            showToast('error', (isZh() ? '无法加载日志: ' : 'Failed to load logs: ') + result.error);
        }
    } catch (err) {
        showToast('error', (isZh() ? '加载日志失败: ' : 'Failed to load logs: ') + err.message);
    }
}

async function cancelTask(taskId) {
    if (!confirm(isZh() ? '确定要取消这个任务吗？' : 'Are you sure you want to cancel this task?')) return;
    try {
        const resp   = await fetch(`/task/${taskId}/cancel`, { method: 'POST' });
        const result = await resp.json();
        if (resp.ok) { showToast('success', isZh() ? '任务已取消' : 'Task cancelled'); refreshTasks(); }
        else          showToast('error', (isZh() ? '取消失败: ' : 'Cancel failed: ') + result.error);
    } catch (err) {
        showToast('error', (isZh() ? '取消失败: ' : 'Cancel failed: ') + err.message);
    }
}

async function deleteTask(taskId) {
    if (!confirm(isZh() ? '确定要删除这个任务吗？此操作将删除所有相关文件且无法恢复。' : 'Are you sure you want to delete this task? All related files will be permanently removed.')) return;
    try {
        const resp   = await fetch(`/task/${taskId}/delete`, { method: 'DELETE' });
        const result = await resp.json();
        if (resp.ok) { showToast('success', isZh() ? '任务已删除' : 'Task deleted'); refreshTasks(); }
        else          showToast('error', (isZh() ? '删除失败: ' : 'Delete failed: ') + result.error);
    } catch (err) {
        showToast('error', (isZh() ? '删除失败: ' : 'Delete failed: ') + err.message);
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
