@echo off
echo Starting Comic Book Collection Manager...
echo.
echo Activating virtual environment...
call .venv\Scripts\activate.bat
echo.
echo Starting application...
echo Open your browser and go to: http://localhost:5000
echo Press Ctrl+C to stop the application
echo.
python app.py
pause
