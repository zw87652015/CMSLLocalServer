@echo off
echo Starting COMSOL Local Server...
echo.
echo This will start the Flask web application.
echo Open your browser to http://localhost:5000 to access the interface.
echo.
echo To process tasks, you need to start the Celery worker in another terminal:
echo python start_worker.py
echo.
python app.py
pause
