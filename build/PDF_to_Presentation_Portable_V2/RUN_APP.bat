@echo off
echo ========================================
echo PDF to Presentation Converter
echo ========================================
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo ❌ Virtual environment not found!
    echo.
    echo Please run SETUP_VENV.bat first to create the virtual environment.
    echo.
    pause
    exit /b 1
)

REM Check if streamlit is installed
if not exist ".venv\Scripts\streamlit.exe" (
    echo ❌ Streamlit not found in virtual environment!
    echo.
    echo Please run SETUP_VENV.bat first to install dependencies.
    echo.
    pause
    exit /b 1
)

echo ✅ Virtual environment found and ready!
echo.
echo Starting application...
echo This will open in your default web browser.
echo If the browser doesn't open automatically, go to: http://localhost:8501
echo.
echo Press Ctrl+C to stop the application when you're done.
echo.

REM Run the application using the virtual environment
".venv\Scripts\python.exe" -m streamlit run "app.py" --server.port 8501 --server.headless true

echo.
echo Application stopped.
pause
