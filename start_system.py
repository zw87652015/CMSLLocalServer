#!/usr/bin/env python3
"""
COMSOL Local Server Starter
Runs Flask app and Celery worker in sequence with proper environment detection
"""

import os
import sys
import subprocess
import time
import threading
from pathlib import Path

def check_conda_available():
    """Check if conda is available in the system"""
    try:
        result = subprocess.run(['conda', '--version'], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def get_conda_environments():
    """Get list of available conda environments"""
    try:
        result = subprocess.run(['conda', 'env', 'list'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            envs = []
            for line in result.stdout.split('\n'):
                if line.strip() and not line.startswith('#'):
                    parts = line.split()
                    if parts:
                        env_name = parts[0]
                        if env_name != 'base':  # Skip base environment
                            envs.append(env_name)
            return envs
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []

def run_flask_app(python_cmd):
    """Run the Flask application"""
    print("🚀 Starting Flask Web Server...")
    try:
        process = subprocess.Popen([python_cmd, 'app.py'], 
                                 cwd=Path(__file__).parent,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT,
                                 universal_newlines=True,
                                 bufsize=1)
        
        # Monitor Flask startup
        startup_timeout = 30
        start_time = time.time()
        
        while True:
            if process.poll() is not None:
                print("❌ Flask app exited unexpectedly")
                return None
                
            if time.time() - start_time > startup_timeout:
                print("⚠️  Flask startup timeout, but continuing...")
                break
                
            time.sleep(1)
            
        print("✅ Flask Web Server started successfully")
        print("   Access at: http://localhost:5000")
        return process
        
    except Exception as e:
        print(f"❌ Failed to start Flask app: {e}")
        return None

def run_celery_worker(python_cmd):
    """Run the Celery worker"""
    print("\n🔧 Starting Celery Worker...")
    try:
        process = subprocess.Popen([python_cmd, 'start_worker.py'],
                                 cwd=Path(__file__).parent,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT,
                                 universal_newlines=True,
                                 bufsize=1)
        
        # Monitor Celery startup
        startup_timeout = 20
        start_time = time.time()
        
        while True:
            if process.poll() is not None:
                print("❌ Celery worker exited unexpectedly")
                return None
                
            if time.time() - start_time > startup_timeout:
                print("⚠️  Celery startup timeout, but continuing...")
                break
                
            time.sleep(1)
            
        print("✅ Celery Worker started successfully")
        return process
        
    except Exception as e:
        print(f"❌ Failed to start Celery worker: {e}")
        return None

def monitor_processes(flask_process, celery_process):
    """Monitor both processes and restart if needed"""
    print("\n📊 Monitoring processes... Press Ctrl+C to stop")
    
    try:
        while True:
            # Check Flask process
            if flask_process and flask_process.poll() is not None:
                print("⚠️  Flask process stopped unexpectedly")
                
            # Check Celery process  
            if celery_process and celery_process.poll() is not None:
                print("⚠️  Celery process stopped unexpectedly")
                
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down processes...")
        
        if flask_process:
            flask_process.terminate()
            try:
                flask_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                flask_process.kill()
                
        if celery_process:
            celery_process.terminate()
            try:
                celery_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                celery_process.kill()
                
        print("✅ All processes stopped")

def main():
    print("=" * 60)
    print("🏭 COMSOL Local Server System Starter")
    print("=" * 60)
    
    # Check if we're in the right directory
    if not Path('app.py').exists() or not Path('start_worker.py').exists():
        print("❌ Error: app.py or start_worker.py not found in current directory")
        print("   Please run this script from the CMSLLocalServer directory")
        sys.exit(1)
    
    # Determine Python command to use
    python_cmd = 'python'
    
    # Check for conda
    if check_conda_available():
        print("🐍 Conda detected!")
        use_conda = input("Do you want to use a conda environment? (y/n): ").lower().strip()
        
        if use_conda in ['y', 'yes']:
            envs = get_conda_environments()
            
            if envs:
                print(f"\n📦 Available conda environments:")
                for i, env in enumerate(envs, 1):
                    print(f"   {i}. {env}")
                
                # Check if cmsl-server exists
                if 'cmsl-server' in envs:
                    print(f"\n💡 Recommended: cmsl-server (found)")
                    default_choice = str(envs.index('cmsl-server') + 1)
                else:
                    default_choice = "1"
                
                choice = input(f"\nSelect environment (1-{len(envs)}) [default: {default_choice}]: ").strip()
                
                if not choice:
                    choice = default_choice
                    
                try:
                    env_index = int(choice) - 1
                    if 0 <= env_index < len(envs):
                        selected_env = envs[env_index]
                        python_cmd = f'conda run -n {selected_env} python'
                        print(f"✅ Using conda environment: {selected_env}")
                    else:
                        print("❌ Invalid choice, using system python")
                except ValueError:
                    print("❌ Invalid input, using system python")
            else:
                print("⚠️  No conda environments found, using system python")
    else:
        print("🐍 Using system Python")
    
    print(f"\n🔧 Python command: {python_cmd}")
    
    # Start Flask app first
    flask_process = run_flask_app(python_cmd)
    if not flask_process:
        print("❌ Failed to start Flask app, exiting")
        sys.exit(1)
    
    # Wait a bit for Flask to fully start
    time.sleep(3)
    
    # Start Celery worker
    celery_process = run_celery_worker(python_cmd)
    if not celery_process:
        print("❌ Failed to start Celery worker")
        if flask_process:
            flask_process.terminate()
        sys.exit(1)
    
    # Monitor both processes
    monitor_processes(flask_process, celery_process)

if __name__ == "__main__":
    main()
