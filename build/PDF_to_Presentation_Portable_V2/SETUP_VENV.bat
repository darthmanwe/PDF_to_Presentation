@echo off
echo ========================================
echo Virtual Environment Setup
echo ========================================
echo.
echo This script will create a virtual environment and install all dependencies.
echo This is a ONE-TIME setup that must be run before using the application.
echo.
echo IMPORTANT: This requires Python to be installed on this computer.
echo RECOMMENDED: Python 3.8 - 3.12 (Python 3.13 may have compatibility issues)
echo If Python is not installed, please install Python 3.8+ first.
echo.
pause

echo.
echo Checking Python installation...
python --version
if %errorlevel% neq 0 (
    echo.
    echo ❌ Python not found! Please install Python 3.8+ first.
    echo You can download Python from: https://python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo.
echo ✅ Python found! Creating virtual environment...
echo This may take a few minutes...

REM Create virtual environment
python -m venv .venv
if %errorlevel% neq 0 (
    echo.
    echo ❌ Failed to create virtual environment!
    echo Please check your Python installation.
    echo.
    pause
    exit /b 1
)

echo ✅ Virtual environment created!

REM Activate virtual environment and install dependencies
echo.
echo Installing dependencies...
echo This may take several minutes depending on your internet speed...

call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo.
    echo ❌ Failed to activate virtual environment!
    echo.
    pause
    exit /b 1
)

echo ✅ Virtual environment activated!

REM Upgrade pip
echo.
echo Upgrading pip...
python -m pip install --upgrade pip
if %errorlevel% neq 0 (
    echo.
    echo ⚠️  Warning: Failed to upgrade pip, continuing anyway...
)

REM Install requirements
echo.
echo Installing required packages...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ❌ Failed to install dependencies!
    echo Please check your internet connection and try again.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo ✅ SETUP COMPLETED SUCCESSFULLY!
echo ========================================
echo.
echo You can now run RUN_APP.bat to start the application.
echo.
echo Note: You only need to run this setup once.
echo If you move this folder to another computer, run SETUP_VENV.bat again.
echo.
pause
