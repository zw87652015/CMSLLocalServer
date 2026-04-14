#!/usr/bin/env python3
"""
CMSL Node Client
================
Run this script on every node computer that should participate in distributed
COMSOL simulation task execution.

Usage
-----
    python node_client.py --server http://192.168.1.10:5000

The client will:
  1. Register with the main server (or re-use saved credentials).
  2. Send a heartbeat every 15 seconds.
  3. Poll for assigned tasks and execute them locally.
  4. Stream progress back to the server.
  5. Upload the result file on completion.

Requirements
------------
  pip install requests psutil

Configuration is stored in node_client_config.json in the same directory.
"""

import argparse
import json
import locale
import logging
import multiprocessing
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Logging — a queue handler lets the GUI receive log records safely
# ---------------------------------------------------------------------------
_log_queue: queue.Queue = queue.Queue()


class _QueueHandler(logging.Handler):
    def emit(self, record):
        _log_queue.put(self.format(record))


_root_handler = _QueueHandler()
_root_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s',
                                              datefmt='%H:%M:%S'))
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger().addHandler(_root_handler)
logger = logging.getLogger('node_client')

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONFIG_FILE = Path(__file__).parent / 'node_client_config.json'

DEFAULT_COMSOL_PATHS = {
    '6.3': r'C:\Program Files\COMSOL\COMSOL63\Multiphysics\bin\win64\comsolbatch.exe',
    '6.2': r'C:\Program Files\COMSOL\COMSOL62\Multiphysics\bin\win64\comsolbatch.exe',
}

HEARTBEAT_INTERVAL = 15   # seconds
POLL_INTERVAL      = 5    # seconds between task polls when idle
PROGRESS_INTERVAL  = 5    # seconds between progress reports to server


def detect_comsol_versions(paths=None):
    """Return a list of COMSOL version strings whose executables exist."""
    if paths is None:
        paths = DEFAULT_COMSOL_PATHS
    return [ver for ver, exe in paths.items() if Path(exe).exists()]


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)


# ---------------------------------------------------------------------------
# Progress parser (same logic as server-side tasks.py)
# ---------------------------------------------------------------------------
class ProgressParser:
    _progress_re = re.compile(r'当前进度:\s*(\d+)\s*%\s*-\s*(.+)')
    _error_patterns = [
        re.compile(r'错误[:：]\s*(.+)'),
        re.compile(r'Error[:：]\s*(.+)', re.IGNORECASE),
        re.compile(r'/\*+错误\*+/'),
        re.compile(r'以下特征遇到问题[:：]'),
        re.compile(r'未定义.*所需的材料属性'),
    ]
    _error_markers = [
        re.compile(r'/\*+错误\*+/'),
        re.compile(r'以下特征遇到问题'),
        re.compile(r'未定义.*所需的材料属性'),
        re.compile(r'ERROR', re.IGNORECASE),
        re.compile(r'FAILED', re.IGNORECASE),
    ]

    @classmethod
    def parse_line(cls, line):
        m = cls._progress_re.search(line)
        if m:
            return float(m.group(1)), m.group(2).strip()
        if '完成' in line and '100' in line:
            return 100.0, '完成'
        return None, None

    @classmethod
    def has_error(cls, output):
        return any(p.search(output) for p in cls._error_markers)

    @classmethod
    def first_error(cls, output):
        for p in cls._error_patterns:
            m = p.search(output)
            if m:
                return m.group(1).strip() if m.groups() else 'COMSOL® simulation error'
        return None


# ---------------------------------------------------------------------------
# Main client class
# ---------------------------------------------------------------------------
class NodeClient:
    def __init__(self, server_url: str, comsol_paths: dict):
        self.server_url       = server_url.rstrip('/')
        self.comsol_paths     = comsol_paths
        self.node_id          = None
        self.auth_token       = None
        self.session          = requests.Session()
        self.session.timeout  = 30
        self._last_heartbeat  = 0.0
        self._current_process = None   # subprocess.Popen while a task runs
        self.abort_event      = threading.Event()  # set to kill current task

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------
    def _headers(self):
        return {
            'X-Node-Id':    self.node_id    or '',
            'X-Node-Token': self.auth_token or '',
        }

    def _get(self, path, **kwargs):
        return self.session.get(
            self.server_url + path,
            headers=self._headers(),
            **kwargs
        )

    def _post(self, path, **kwargs):
        return self.session.post(
            self.server_url + path,
            headers=self._headers(),
            **kwargs
        )

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(self):
        hostname        = socket.gethostname()
        comsol_versions = detect_comsol_versions(self.comsol_paths)
        cpu_cores       = multiprocessing.cpu_count()

        if not comsol_versions:
            logger.warning(
                'No COMSOL executables found at expected paths. '
                'Node will register but may not accept tasks for any version.'
            )

        payload = {
            'hostname':        hostname,
            'comsol_versions': comsol_versions,
            'cpu_cores':       cpu_cores,
        }
        logger.info('Registering with server %s as %s (COMSOL: %s, cores: %d) ...',
                    self.server_url, hostname, comsol_versions, cpu_cores)
        resp = self.session.post(
            self.server_url + '/api/nodes/register',
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        data            = resp.json()
        self.node_id    = data['node_id']
        self.auth_token = data['auth_token']
        logger.info('Registered. node_id=%s', self.node_id)

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------
    def heartbeat(self, status='online') -> bool:
        """Send a heartbeat.
        Returns True on success, False on network/server error.
        Raises PermissionError if the server returns 401 (stale credentials)."""
        try:
            resp = self._post('/api/nodes/heartbeat', json={'status': status})
            if resp.status_code == 401:
                raise PermissionError('Credentials rejected by server (401)')
            resp.raise_for_status()
            self._last_heartbeat = time.time()
            return True
        except PermissionError:
            raise
        except Exception as exc:
            logger.warning('Heartbeat failed: %s', exc)
            return False

    def _maybe_heartbeat(self, status='online'):
        if time.time() - self._last_heartbeat >= HEARTBEAT_INTERVAL:
            self.heartbeat(status)

    # ------------------------------------------------------------------
    # Task polling
    # ------------------------------------------------------------------
    def poll_task(self):
        """Ask the server for the next task assigned to this node.
        Returns the task dict or None.
        Raises PermissionError on 401 (stale credentials)."""
        try:
            resp = self._get('/api/nodes/task/poll')
            if resp.status_code == 401:
                raise PermissionError('Credentials rejected by server (401)')
            resp.raise_for_status()
            return resp.json().get('task')
        except PermissionError:
            raise
        except Exception as exc:
            logger.warning('Poll failed: %s', exc)
            return None

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------
    def execute_task(self, task_info: dict):
        task_id       = task_info['id']
        comsol_ver    = task_info['comsol_version']
        cpu_cores     = task_info.get('cpu_cores', multiprocessing.cpu_count())
        input_url     = task_info['input_file_url']
        unique_fname  = task_info['unique_filename']

        logger.info('Received task %s (COMSOL %s)', task_id, comsol_ver)

        # --- Download input file ---
        work_dir = Path(__file__).parent / 'node_workdir'
        work_dir.mkdir(exist_ok=True)
        input_path  = work_dir / unique_fname
        output_name = Path(unique_fname).stem + '_solved.mph'
        output_path = work_dir / output_name

        try:
            logger.info('Downloading input file ...')
            resp = self._get(input_url, stream=True, timeout=120)
            resp.raise_for_status()
            with open(input_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
            logger.info('Input file saved: %s', input_path)
        except Exception as exc:
            self._report_fail(task_id, f'Failed to download input file: {exc}', '')
            return

        # --- Find COMSOL executable ---
        comsol_exe = self.comsol_paths.get(comsol_ver)
        if not comsol_exe or not Path(comsol_exe).exists():
            msg = f'COMSOL {comsol_ver} not found at {comsol_exe}'
            logger.error(msg)
            self._report_fail(task_id, msg, '')
            return

        # --- Report start ---
        self.abort_event.clear()
        try:
            self._post(f'/api/nodes/task/{task_id}/start', json={}).raise_for_status()
        except Exception as exc:
            logger.warning('Could not report task start: %s', exc)

        self.heartbeat(status='busy')

        # --- Run COMSOL ---
        cmd = [
            comsol_exe,
            '-np', str(cpu_cores),
            '-inputfile', str(input_path),
            '-outputfile', str(output_path),
        ]
        logger.info('Running: %s', ' '.join(cmd))

        system_encoding = locale.getpreferredencoding()
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
            encoding=system_encoding,
            errors='replace',
        )
        self._current_process = process

        # Report PID so server can show it (best-effort)
        try:
            self._post(f'/api/nodes/task/{task_id}/start',
                       json={'process_id': process.pid})
        except Exception:
            pass

        # ── Read stdout in a background thread so the main thread can poll
        # abort_event and the server cancel flag without blocking on I/O.
        stdout_q: queue.Queue = queue.Queue()

        def _stdout_reader():
            for raw_line in process.stdout:
                stdout_q.put(raw_line)
            stdout_q.put(None)  # sentinel: process exited

        threading.Thread(target=_stdout_reader, daemon=True,
                         name='comsol-reader').start()

        output_lines  = []
        last_progress = 0.0
        last_report_t = time.time()
        last_step     = None
        aborted       = False

        while True:
            # Poll abort every 2 s even if COMSOL produces no output
            try:
                raw = stdout_q.get(timeout=2.0)
            except queue.Empty:
                raw = ...   # timeout sentinel — do the periodic checks below

            # ── Abort check (Stop button or prior server cancel signal) ──
            if self.abort_event.is_set():
                logger.warning('Abort requested — killing COMSOL process.')
                process.kill()
                aborted = True
                break

            # ── Periodic server-side cancel check (every PROGRESS_INTERVAL) ──
            now = time.time()
            if now - last_report_t >= PROGRESS_INTERVAL:
                if self._report_progress(task_id, last_progress, last_step):
                    logger.warning('Server requested abort for task %s.', task_id)
                    process.kill()
                    aborted = True
                    break
                last_report_t = now

            if raw is None:
                break       # process exited normally
            if raw is ...:
                continue    # was a timeout — no line to process

            # ── Process the output line ──
            line = raw.strip()
            output_lines.append(line)
            self._maybe_heartbeat('busy')

            pct, step = ProgressParser.parse_line(line)
            if pct is not None and pct > last_progress:
                last_progress = pct
                last_step     = step

        return_code  = process.wait()
        self._current_process = None

        if aborted:
            logger.info('Task %s aborted.', task_id)
            # Upload whatever output was captured before the kill
            partial_log = '\n'.join(output_lines)
            if partial_log:
                try:
                    self._post(f'/api/nodes/task/{task_id}/upload_log',
                               json={'log_text': partial_log[-2_000_000:]})
                    logger.info('Partial log uploaded for aborted task %s.', task_id)
                except Exception as exc:
                    logger.warning('Could not upload partial log: %s', exc)
            for p in (input_path, output_path):
                try:
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass
            return

        full_output  = '\n'.join(output_lines)

        # --- Evaluate result ---
        if return_code == 0 and not ProgressParser.has_error(full_output):
            if output_path.exists():
                logger.info('Task %s completed. Uploading result ...', task_id)
                self._report_complete(task_id, output_path, log_text=full_output)
            else:
                msg = 'COMSOL finished but output file is missing'
                logger.error(msg)
                self._report_fail(task_id, msg, full_output)
        else:
            error_msg = (
                ProgressParser.first_error(full_output)
                or f'COMSOL exited with code {return_code}'
            )
            logger.error('Task %s failed: %s', task_id, error_msg)
            self._report_fail(task_id, error_msg, full_output)

        # --- Cleanup local work files ---
        for p in (input_path, output_path):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Report helpers
    # ------------------------------------------------------------------
    def _report_progress(self, task_id, percentage, step=None) -> bool:
        """Send a progress update.  Returns True if the server wants this task aborted."""
        try:
            resp = self._post(
                f'/api/nodes/task/{task_id}/progress',
                json={'percentage': percentage, 'step': step or ''},
            )
            if resp.status_code == 404:
                return True   # task was deleted server-side
            if resp.ok:
                return bool(resp.json().get('cancel'))
        except Exception as exc:
            logger.warning('Progress report failed: %s', exc)
        return False

    def _post_with_retry(self, path, max_attempts=4, **kwargs):
        """POST with exponential backoff.
        4xx responses are NOT retried — they indicate a permanent client-side
        error (e.g. task deleted on server).  Only network errors and 5xx are
        retried.  Returns the Response or raises."""
        import requests as _requests
        delay = 5
        last_exc = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._post(path, **kwargs)
                if 400 <= resp.status_code < 500:
                    # Client error — no point retrying
                    resp.raise_for_status()
                resp.raise_for_status()
                return resp
            except _requests.HTTPError as exc:
                # 4xx already raised above (single attempt); re-raise immediately
                if exc.response is not None and 400 <= exc.response.status_code < 500:
                    raise
                last_exc = exc
            except Exception as exc:
                last_exc = exc
            if attempt < max_attempts:
                logger.warning('Attempt %d/%d failed (%s). Retrying in %ds …',
                               attempt, max_attempts, last_exc, delay)
                time.sleep(delay)
                delay = min(delay * 2, 60)
        raise last_exc

    def _report_complete(self, task_id, result_path: Path, log_text: str = ''):
        # Step 1 — tell the server the task is done (and upload log text).
        # This always runs and is retried; status is updated even if
        # the file upload later fails.
        _LOG_CAP = 2_000_000  # 2 MB of text max
        try:
            self._post_with_retry(f'/api/nodes/task/{task_id}/complete',
                                  json={'completed': True,
                                        'log_text': log_text[-_LOG_CAP:]})
            logger.info('Task %s marked completed on server.', task_id)
        except Exception as exc:
            logger.error('Could not mark task %s complete: %s', task_id, exc)
            # Still attempt the file upload below — the server may accept it.

        # Step 2 — upload result file separately (best-effort).
        if result_path and result_path.exists():
            try:
                with open(result_path, 'rb') as f:
                    self._post_with_retry(
                        f'/api/nodes/task/{task_id}/upload_result',
                        files={'result_file': (result_path.name, f,
                                               'application/octet-stream')},
                        timeout=300,
                    )
                logger.info('Result file uploaded for task %s.', task_id)
            except Exception as exc:
                logger.error('Result file upload failed for task %s: %s — '
                             'task is still marked complete but no download '
                             'link will be available.', task_id, exc)
        else:
            logger.warning('No result file to upload for task %s.', task_id)

    def _report_fail(self, task_id, error_message, error_log):
        try:
            self._post_with_retry(
                f'/api/nodes/task/{task_id}/fail',
                json={'error_message': error_message,
                      'error_log': error_log[-10000:]},  # cap log size
            )
        except Exception as exc:
            logger.error('Could not report failure for task %s: %s', task_id, exc)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self):
        # Load saved credentials (survive restarts without re-registering)
        cfg = load_config()
        if cfg.get('server_url') == self.server_url and cfg.get('node_id'):
            self.node_id    = cfg['node_id']
            self.auth_token = cfg['auth_token']
            logger.info('Loaded saved credentials. node_id=%s', self.node_id)
        else:
            self.register()
            save_config({
                'server_url': self.server_url,
                'node_id':    self.node_id,
                'auth_token': self.auth_token,
            })

        # Initial heartbeat — if 401, saved credentials are stale; re-register
        try:
            self.heartbeat()
        except PermissionError:
            logger.warning('Saved credentials rejected. Re-registering…')
            self.node_id = None
            self.auth_token = None
            self.register()
            save_config({
                'server_url': self.server_url,
                'node_id':    self.node_id,
                'auth_token': self.auth_token,
            })
            self.heartbeat()

        logger.info('Node client running. Polling every %d s ...', POLL_INTERVAL)

        while True:
            try:
                self._maybe_heartbeat()
                task = self.poll_task()
                if task:
                    self.execute_task(task)
                    self.heartbeat('online')
                else:
                    time.sleep(POLL_INTERVAL)
            except KeyboardInterrupt:
                logger.info('Shutting down.')
                break
            except Exception as exc:
                logger.error('Unexpected error in main loop: %s', exc, exc_info=True)
                time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
COMSOL_VERSIONS = ['6.3', '6.2']


def _normalise_url(url: str) -> str:
    """Strip trailing slash and fix accidental double-scheme like http://http://…"""
    url = url.strip()
    for scheme in ('https://', 'http://'):
        while url.lower().startswith(scheme + scheme[:-2]):
            url = scheme + url[len(scheme):]
    return url.rstrip('/')


class NodeClientGUI:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk, filedialog, scrolledtext

        self._tk           = tk
        self._filedialog   = filedialog
        self.root          = root
        self._client       = None
        self._worker       = None
        self._stop_event   = threading.Event()

        root.title('CMSL Node Client')
        root.resizable(False, False)

        # ── load persisted settings ──────────────────────────────────────
        cfg = load_config()

        # ── layout ───────────────────────────────────────────────────────
        pad = dict(padx=10, pady=4)

        # -- Server URL --
        frm_srv = ttk.LabelFrame(root, text='Server')
        frm_srv.pack(fill='x', **pad)

        ttk.Label(frm_srv, text='URL:').grid(row=0, column=0, sticky='w', padx=6, pady=6)
        self._server_var = tk.StringVar(value=cfg.get('server_url', 'http://'))
        ttk.Entry(frm_srv, textvariable=self._server_var, width=42).grid(
            row=0, column=1, padx=6, pady=6, sticky='ew')
        frm_srv.columnconfigure(1, weight=1)

        # -- COMSOL paths --
        frm_comsol = ttk.LabelFrame(root, text='COMSOL Executables')
        frm_comsol.pack(fill='x', **pad)

        self._comsol_vars    = {}
        self._comsol_status  = {}
        saved_paths = cfg.get('comsol_paths', {})

        for row_i, ver in enumerate(COMSOL_VERSIONS):
            default_path = saved_paths.get(ver, DEFAULT_COMSOL_PATHS.get(ver, ''))
            var = tk.StringVar(value=default_path)
            self._comsol_vars[ver] = var

            ttk.Label(frm_comsol, text=f'v{ver}:').grid(
                row=row_i, column=0, sticky='w', padx=6, pady=4)

            entry = ttk.Entry(frm_comsol, textvariable=var, width=36)
            entry.grid(row=row_i, column=1, padx=4, pady=4, sticky='ew')
            var.trace_add('write', lambda *_, v=ver: self._refresh_exe_status(v))

            ttk.Button(frm_comsol, text='Browse…',
                       command=lambda v=ver: self._browse_comsol(v)).grid(
                row=row_i, column=2, padx=4)

            status_lbl = ttk.Label(frm_comsol, text='', width=2)
            status_lbl.grid(row=row_i, column=3, padx=(0, 6))
            self._comsol_status[ver] = status_lbl

            self._refresh_exe_status(ver)

        frm_comsol.columnconfigure(1, weight=1)

        # -- Status bar --
        frm_status = ttk.Frame(root)
        frm_status.pack(fill='x', padx=10, pady=(6, 2))

        self._status_lbl = ttk.Label(frm_status, text='● Stopped', foreground='gray')
        self._status_lbl.pack(side='left')

        self._node_lbl = ttk.Label(frm_status, text='', foreground='#555')
        self._node_lbl.pack(side='left', padx=10)

        # -- Buttons --
        frm_btn = ttk.Frame(root)
        frm_btn.pack(fill='x', padx=10, pady=4)

        self._btn_start = ttk.Button(frm_btn, text='Start', command=self._start)
        self._btn_start.pack(side='left', padx=(0, 6))

        self._btn_stop = ttk.Button(frm_btn, text='Stop', command=self._stop,
                                    state='disabled')
        self._btn_stop.pack(side='left')

        # -- Log area --
        frm_log = ttk.LabelFrame(root, text='Log')
        frm_log.pack(fill='both', expand=True, padx=10, pady=(4, 10))

        self._log_text = scrolledtext.ScrolledText(
            frm_log, width=70, height=18, state='disabled',
            font=('Consolas', 9), wrap='word',
            background='#1e1e1e', foreground='#d4d4d4',
            insertbackground='white',
        )
        self._log_text.pack(fill='both', expand=True, padx=4, pady=4)
        # colour tags
        self._log_text.tag_config('warn',  foreground='#e5c07b')
        self._log_text.tag_config('error', foreground='#e06c75')
        self._log_text.tag_config('info',  foreground='#98c379')

        # -- poll log queue --
        self._poll_log()

        root.protocol('WM_DELETE_WINDOW', self._on_close)

    # ── helpers ─────────────────────────────────────────────────────────────

    def _refresh_exe_status(self, ver):
        path = self._comsol_vars[ver].get().strip()
        exists = path and Path(path).exists()
        lbl = self._comsol_status[ver]
        lbl.config(text='✔' if exists else '✘',
                   foreground='#4caf50' if exists else '#e57373')

    def _browse_comsol(self, ver):
        path = self._filedialog.askopenfilename(
            title=f'Select comsolbatch.exe for COMSOL {ver}',
            filetypes=[('Executable', '*.exe'), ('All files', '*.*')],
            initialdir=Path(self._comsol_vars[ver].get()).parent
                       if self._comsol_vars[ver].get() else 'C:\\',
        )
        if path:
            self._comsol_vars[ver].set(path)

    def _append_log(self, text: str):
        self._log_text.config(state='normal')
        tag = 'error' if '[ERROR]' in text else 'warn' if '[WARNING]' in text else 'info'
        self._log_text.insert('end', text + '\n', tag)
        self._log_text.see('end')
        self._log_text.config(state='disabled')

    def _poll_log(self):
        try:
            while True:
                msg = _log_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        self.root.after(200, self._poll_log)

    def _save_settings(self):
        cfg = load_config()
        cfg['server_url']   = _normalise_url(self._server_var.get())
        cfg['comsol_paths'] = {v: self._comsol_vars[v].get().strip()
                               for v in COMSOL_VERSIONS}
        save_config(cfg)

    # ── start / stop ────────────────────────────────────────────────────────

    def _start(self):
        server_url = _normalise_url(self._server_var.get())
        if not server_url or server_url in ('http://', 'https://'):
            self._append_log('[ERROR] Please enter a valid server URL.')
            return

        self._save_settings()

        comsol_paths = {v: self._comsol_vars[v].get().strip()
                        for v in COMSOL_VERSIONS
                        if self._comsol_vars[v].get().strip()}

        self._stop_event.clear()
        self._client = NodeClient(server_url=server_url,
                                  comsol_paths=comsol_paths)

        self._worker = threading.Thread(
            target=self._run_client, daemon=True, name='node-client')
        self._worker.start()

        self._btn_start.config(state='disabled')
        self._btn_stop.config(state='normal')
        self._status_lbl.config(text='● Running', foreground='#4caf50')

    def _run_client(self):
        """Runs NodeClient.run() on the worker thread; patches its loop to
        honour _stop_event so Stop works cleanly."""
        client = self._client
        cfg    = load_config()

        # Restore saved credentials when server URL matches
        if cfg.get('server_url') == client.server_url and cfg.get('node_id'):
            client.node_id    = cfg['node_id']
            client.auth_token = cfg['auth_token']
            logger.info('Loaded saved credentials. node_id=%s', client.node_id)
        else:
            try:
                client.register()
            except Exception as exc:
                logger.error('Registration failed: %s', exc)
                self.root.after(0, self._on_worker_stopped)
                return
            cfg = {**cfg, 'server_url': client.server_url,
                   'node_id': client.node_id, 'auth_token': client.auth_token}
            save_config(cfg)

        # Initial heartbeat — if 401, saved credentials are stale; re-register
        try:
            client.heartbeat()
        except PermissionError:
            logger.warning('Saved credentials rejected. Re-registering…')
            client.node_id = None
            client.auth_token = None
            try:
                client.register()
            except Exception as exc:
                logger.error('Re-registration failed: %s', exc)
                self.root.after(0, self._on_worker_stopped)
                return
            cfg = {**cfg, 'server_url': client.server_url,
                   'node_id': client.node_id, 'auth_token': client.auth_token}
            save_config(cfg)
            client.heartbeat()

        # Update node label in UI
        self.root.after(0, lambda: self._node_lbl.config(
            text=f'node_id: {client.node_id[:8]}…'))

        logger.info('Node client running. Polling every %d s …', POLL_INTERVAL)

        while not self._stop_event.is_set():
            try:
                client._maybe_heartbeat()
                task = client.poll_task()
                if task:
                    client.execute_task(task)
                    client.heartbeat('online')
                else:
                    self._stop_event.wait(POLL_INTERVAL)
            except PermissionError:
                # Server rejected our credentials mid-session (e.g. DB reset)
                logger.warning('Got 401 mid-session. Re-registering…')
                client.node_id = None
                client.auth_token = None
                try:
                    client.register()
                    cfg2 = load_config()
                    save_config({**cfg2, 'server_url': client.server_url,
                                 'node_id': client.node_id,
                                 'auth_token': client.auth_token})
                    self.root.after(0, lambda: self._node_lbl.config(
                        text=f'node_id: {client.node_id[:8]}…'))
                except Exception as exc2:
                    logger.error('Re-registration failed: %s', exc2)
                    self._stop_event.wait(POLL_INTERVAL)
            except Exception as exc:
                logger.error('Unexpected error: %s', exc, exc_info=True)
                self._stop_event.wait(POLL_INTERVAL)

        logger.info('Node client stopped.')
        self.root.after(0, self._on_worker_stopped)

    def _stop(self):
        self._stop_event.set()
        self._btn_stop.config(state='disabled')
        self._status_lbl.config(text='● Stopping…', foreground='#e5c07b')
        # Kill the running COMSOL subprocess immediately so the worker exits fast
        if self._client:
            self._client.abort_event.set()
            proc = self._client._current_process
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _on_worker_stopped(self):
        self._btn_start.config(state='normal')
        self._btn_stop.config(state='disabled')
        self._status_lbl.config(text='● Stopped', foreground='gray')
        self._node_lbl.config(text='')

    def _on_close(self):
        self._stop_event.set()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Entry point — GUI by default, headless if --server is passed
# ---------------------------------------------------------------------------
def main():
    # Headless / CLI mode when --server is explicitly provided
    if '--server' in sys.argv:
        parser = argparse.ArgumentParser(
            description='CMSL Node Client — run on each compute node.'
        )
        parser.add_argument('--server', required=True,
                            help='Base URL of the main server')
        parser.add_argument('--comsol-63', default=DEFAULT_COMSOL_PATHS.get('6.3'))
        parser.add_argument('--comsol-62', default=DEFAULT_COMSOL_PATHS.get('6.2'))
        args = parser.parse_args()

        comsol_paths = {'6.3': args.comsol_63, '6.2': args.comsol_62}
        client = NodeClient(server_url=_normalise_url(args.server),
                            comsol_paths=comsol_paths)
        client.run()
        return

    # GUI mode
    import tkinter as tk
    from tkinter import ttk  # noqa: F401 — ensures ttk theme loads before NodeClientGUI

    root = tk.Tk()
    try:
        root.tk.call('tk', 'scaling', 1.25)
    except Exception:
        pass
    NodeClientGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
