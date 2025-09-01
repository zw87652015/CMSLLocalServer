@echo off
setlocal enabledelayedexpansion
REM COMSOL Local Server System Starter (Windows Batch Version)
REM Runs Flask app and Celery worker with environment detection

title COMSOL Local Server Starter

echo ============================================================
echo COMSOL Local Server System Starter
echo ============================================================

REM Check if we're in the right directory
if not exist "app.py" (
    echo Error: app.py not found in current directory
    echo Please run this script from the CMSLLocalServer directory
    pause
    exit /b 1
)

if not exist "start_worker.py" (
    echo Error: start_worker.py not found in current directory
    echo Please run this script from the CMSLLocalServer directory
    pause
    exit /b 1
)

REM Check for conda
where conda >nul 2>&1
if !errorlevel! == 0 (
    echo Conda detected!
    set /p use_conda="Do you want to use a conda environment? (y/n): "
    
    if /i "!use_conda!"=="y" (
        echo.
        echo Available conda environments:
        conda env list | findstr /v "^#" | findstr /v "base"
        echo.
        echo Recommended: cmsl-server (if available)
        set /p conda_env="Enter environment name [default: cmsl-server]: "
        
        if "!conda_env!"=="" set conda_env=cmsl-server
        
        echo Using conda environment: !conda_env!
        REM Get conda installation path
        for /f "tokens=*" %%i in ('conda info --base') do set "conda_base=%%i"
    ) else (
        echo Using system Python
    )
) else (
    echo Using system Python
)

REM Start Flask app in new terminal window
if defined conda_env (
    set "activate_script=!conda_base!\Scripts\activate.bat"
    set "flask_command=call "!activate_script!" !conda_env! && python app.py"
    set "celery_command=call "!activate_script!" !conda_env! && python start_worker.py"
) else (
    set "flask_command=python app.py"
    set "celery_command=python start_worker.py"
)

REM Start Flask app in new terminal window
echo Starting Flask Web Server...
start "Flask Server" cmd /k "%flask_command%"

REM Wait a bit for Flask to start
timeout /t 5 /nobreak >nul

REM Start Celery worker in new terminal window
echo Starting Celery Worker...
start "Celery Worker" cmd /k "%celery_command%"

echo.
echo Both services are starting in separate windows...
echo Flask Web Server: http://localhost:5000
echo Celery Worker: Processing tasks
echo.
echo Two new terminal windows should have opened:
echo 1. Flask Server - Shows web server logs
echo 2. Celery Worker - Shows task processing logs
echo.
echo To stop the services:
echo - Press Ctrl+C in each terminal window, OR
echo - Close the terminal windows directly, OR
echo - Use Task Manager to end python processes
echo.
echo Press any key to exit this launcher (services will keep running)
pause >nul
