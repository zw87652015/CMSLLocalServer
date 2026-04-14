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
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
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
        self.server_url    = server_url.rstrip('/')
        self.comsol_paths  = comsol_paths
        self.node_id       = None
        self.auth_token    = None
        self.session       = requests.Session()
        self.session.timeout = 30
        self._last_heartbeat = 0.0

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
    def heartbeat(self, status='online'):
        try:
            resp = self._post('/api/nodes/heartbeat', json={'status': status})
            resp.raise_for_status()
            self._last_heartbeat = time.time()
        except Exception as exc:
            logger.warning('Heartbeat failed: %s', exc)

    def _maybe_heartbeat(self, status='online'):
        if time.time() - self._last_heartbeat >= HEARTBEAT_INTERVAL:
            self.heartbeat(status)

    # ------------------------------------------------------------------
    # Task polling
    # ------------------------------------------------------------------
    def poll_task(self):
        """Ask the server for the next task assigned to this node.
        Returns the task dict or None."""
        try:
            resp = self._get('/api/nodes/task/poll')
            resp.raise_for_status()
            return resp.json().get('task')
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

        output_lines    = []
        last_progress   = 0.0
        last_report_t   = time.time()

        for line in process.stdout:
            line = line.strip()
            output_lines.append(line)
            self._maybe_heartbeat('busy')

            pct, step = ProgressParser.parse_line(line)
            if pct is not None and pct > last_progress:
                last_progress = pct
                if time.time() - last_report_t >= PROGRESS_INTERVAL:
                    self._report_progress(task_id, pct, step)
                    last_report_t = time.time()

        return_code  = process.wait()
        full_output  = '\n'.join(output_lines)

        # --- Evaluate result ---
        if return_code == 0 and not ProgressParser.has_error(full_output):
            if output_path.exists():
                logger.info('Task %s completed. Uploading result ...', task_id)
                self._report_complete(task_id, output_path)
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
    def _report_progress(self, task_id, percentage, step=None):
        try:
            self._post(
                f'/api/nodes/task/{task_id}/progress',
                json={'percentage': percentage, 'step': step or ''},
            )
        except Exception as exc:
            logger.warning('Progress report failed: %s', exc)

    def _report_complete(self, task_id, result_path: Path):
        try:
            with open(result_path, 'rb') as f:
                resp = self._post(
                    f'/api/nodes/task/{task_id}/complete',
                    files={'result_file': (result_path.name, f, 'application/octet-stream')},
                    timeout=300,  # large files may take a while
                )
            resp.raise_for_status()
            logger.info('Result uploaded for task %s', task_id)
        except Exception as exc:
            logger.error('Failed to upload result for task %s: %s', task_id, exc)

    def _report_fail(self, task_id, error_message, error_log):
        try:
            self._post(
                f'/api/nodes/task/{task_id}/fail',
                json={'error_message': error_message, 'error_log': error_log},
            )
        except Exception as exc:
            logger.warning('Failed to report task failure: %s', exc)

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
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='CMSL Node Client — run on each compute node.'
    )
    parser.add_argument(
        '--server', required=True,
        help='Base URL of the main server, e.g. http://192.168.1.10:5000'
    )
    parser.add_argument(
        '--comsol-63',
        default=DEFAULT_COMSOL_PATHS.get('6.3'),
        help='Path to comsolbatch.exe for COMSOL 6.3'
    )
    parser.add_argument(
        '--comsol-62',
        default=DEFAULT_COMSOL_PATHS.get('6.2'),
        help='Path to comsolbatch.exe for COMSOL 6.2'
    )
    args = parser.parse_args()

    comsol_paths = {
        '6.3': args.comsol_63,
        '6.2': args.comsol_62,
    }

    client = NodeClient(server_url=args.server, comsol_paths=comsol_paths)
    client.run()


if __name__ == '__main__':
    main()
