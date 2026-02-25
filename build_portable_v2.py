#!/usr/bin/env python3
"""
Portable Application Builder V2
Creates a self-contained folder with installation packages and clean venv builder.
The virtual environment is created on the target machine, not copied from source.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

def create_portable_app():
    """Create a portable application folder with installation packages"""
    
    print("🚀 Building Portable Application V2...")
    
    # Configuration
    app_name = "PDF_to_Presentation_Portable_V2"
    source_dir = Path.cwd()
    build_dir = source_dir / "build" / app_name
    
    # Clean previous build
    if build_dir.exists():
        shutil.rmtree(build_dir)
    
    # Create build directory
    build_dir.mkdir(parents=True, exist_ok=True)
    
    # IMPORTANT: Ensure no .venv folder exists in the build
    venv_in_build = build_dir / ".venv"
    if venv_in_build.exists():
        shutil.rmtree(venv_in_build)
        print("  🗑️  Removed existing .venv folder from build")
    
    print(f"📁 Build directory: {build_dir}")
    
    # Copy source files
    source_files = [
        "app.py",
        "main_processor.py", 
        "llm_agent.py",
        "pdf_processor.py",
        "translation_service.py",
        "presentation_builder.py",
        "config.py",
        "requirements.txt",
        ".env",
        "README.md"
    ]
    
    print("📋 Copying source files...")
    for file_name in source_files:
        source_path = source_dir / file_name
        if source_path.exists():
            shutil.copy2(source_path, build_dir)
            print(f"  ✅ {file_name}")
        else:
            print(f"  ❌ {file_name} (not found)")
    
    # Create launcher scripts
    print("📝 Creating launcher scripts...")
    
    # Windows launcher
    windows_launcher = build_dir / "RUN_APP.bat"
    with open(windows_launcher, 'w', encoding='utf-8') as f:
        f.write("""@echo off
echo ========================================
echo PDF to Presentation Converter
echo ========================================
echo.

REM Check if virtual environment exists
if not exist ".venv\\Scripts\\python.exe" (
    echo ❌ Virtual environment not found!
    echo.
    echo Please run SETUP_VENV.bat first to create the virtual environment.
    echo.
    pause
    exit /b 1
)

REM Check if streamlit is installed
if not exist ".venv\\Scripts\\streamlit.exe" (
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
".venv\\Scripts\\python.exe" -m streamlit run "app.py" --server.port 8501 --server.headless true

echo.
echo Application stopped.
pause
""")
    
    # Python launcher
    python_launcher = build_dir / "run_app.py"
    with open(python_launcher, 'w', encoding='utf-8') as f:
        f.write("""#!/usr/bin/env python3
\"\"\"
Python launcher for PDF to Presentation Converter
Uses the virtual environment created by SETUP_VENV.bat
\"\"\"

import subprocess
import sys
import os
from pathlib import Path

def main():
    print("Starting PDF to Presentation Converter...")
    print("This will open in your default web browser.")
    print("Please wait...")
    
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    
    # Paths to virtual environment executables
    venv_python = script_dir / ".venv" / "Scripts" / "python.exe"
    venv_streamlit = script_dir / ".venv" / "Scripts" / "streamlit.exe"
    
    # Check if virtual environment exists
    if not venv_python.exists():
        print(f"ERROR: Virtual environment Python not found at: {venv_python}")
        print("Please run SETUP_VENV.bat first to create the virtual environment.")
        input("Press Enter to exit...")
        return
    
    if not venv_streamlit.exists():
        print(f"ERROR: Streamlit not found in virtual environment at: {venv_streamlit}")
        print("Please run SETUP_VENV.bat first to install dependencies.")
        input("Press Enter to exit...")
        return
    
    print(f"Using Python from: {venv_python}")
    print(f"Using Streamlit from: {venv_streamlit}")
    print()
    
    try:
        # Run Streamlit using the virtual environment's Python
        subprocess.run([
            str(venv_python), "-m", "streamlit", "run", str(script_dir / "app.py"),
            "--server.port", "8501",
            "--server.headless", "true"
        ])
    except KeyboardInterrupt:
        print("\\nApplication stopped by user.")
    except Exception as e:
        print(f"Error: {e}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
""")
    
    # Create virtual environment setup script
    print("🔧 Creating virtual environment setup script...")
    setup_venv = build_dir / "SETUP_VENV.bat"
    with open(setup_venv, 'w', encoding='utf-8') as f:
        f.write("""@echo off
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

call .venv\\Scripts\\activate.bat
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
""")
    
    # Create user guide
    print("📚 Creating user guide...")
    user_guide = build_dir / "HOW_TO_USE.txt"
    with open(user_guide, 'w', encoding='utf-8') as f:
        f.write("""PDF TO PRESENTATION CONVERTER - PORTABLE VERSION V2
================================================================

IMPORTANT: FIRST-TIME SETUP REQUIRED!
=====================================

This application requires a ONE-TIME setup before it can be used.
Follow these steps carefully:

STEP 1: FIRST-TIME SETUP
=========================

1. Make sure Python 3.8+ is installed on this computer
   - If not installed, download from: https://python.org/downloads/
   - During installation, CHECK "Add Python to PATH"

2. DOUBLE-CLICK "SETUP_VENV.bat"
   - This will create a virtual environment and install dependencies
   - This process may take 5-10 minutes depending on internet speed
   - Wait for "SETUP COMPLETED SUCCESSFULLY!" message

3. You only need to run SETUP_VENV.bat ONCE per computer
   - If you move this folder to another computer, run it again there

STEP 2: RUNNING THE APPLICATION
===============================

1. After setup is complete, DOUBLE-CLICK "RUN_APP.bat"
   - This will start the application
   - A web browser will open automatically
   - If no browser opens, go to: http://localhost:8501

2. UPLOAD YOUR PDF:
   - Click "Browse files" to select your PDF
   - Choose language (English or Turkish)
   - Select "Text-Only Operation" for faster processing (recommended for medical texts)
   - Click "Convert PDF to Presentation"

3. DOWNLOAD YOUR PRESENTATION:
   - Wait for processing to complete
   - Click the download link for your .pptx file

4. TO STOP THE APPLICATION:
   - Press Ctrl+C in the command window
   - Or close the command window

TROUBLESHOOTING:
================

- If you get "Python not found" error:
  Install Python 3.8+ from https://python.org/downloads/
  Make sure to check "Add Python to PATH" during installation

- If SETUP_VENV.bat fails:
  Check your internet connection
  Try running as administrator (right-click → "Run as administrator")

- If RUN_APP.bat says "Virtual environment not found":
  Run SETUP_VENV.bat first

- If the browser doesn't open:
  Manually go to: http://localhost:8501

- If you get permission errors:
  Right-click the .bat files and "Run as administrator"

FILES IN THIS FOLDER:
====================

- SETUP_VENV.bat: FIRST-TIME SETUP (run this first!)
- RUN_APP.bat: Application launcher (run after setup)
- run_app.py: Python launcher (alternative)
- app.py: Main application
- .env: Configuration file (keep this!)
- requirements.txt: Package list for setup
- All other files: Application components

SUPPORT:
========

If you have issues, check that:
1. Python 3.8+ is installed and added to PATH
2. All files are in the same folder
3. The .env file contains your Azure API keys
4. You have an internet connection for the initial setup
5. Your antivirus isn't blocking the application

Happy converting!
""")
    
    # Create a simple test script
    print("🧪 Creating test script...")
    test_script = build_dir / "TEST_VENV.bat"
    with open(test_script, 'w', encoding='utf-8') as f:
        f.write("""@echo off
echo ========================================
echo Virtual Environment Test
echo ========================================
echo.

if not exist ".venv\\Scripts\\python.exe" (
    echo ❌ Virtual environment not found!
    echo Please run SETUP_VENV.bat first.
    pause
    exit /b 1
)

echo ✅ Virtual environment found!

echo.
echo Testing Python...
".venv\\Scripts\\python.exe" --version

echo.
echo Testing package imports...
".venv\\Scripts\\python.exe" -c "import streamlit; print('✅ Streamlit imported successfully')"
".venv\\Scripts\\python.exe" -c "import fitz; print('✅ PyMuPDF imported successfully')"
".venv\\Scripts\\python.exe" -c "import pptx; print('✅ python-pptx imported successfully')"
".venv\\Scripts\\python.exe" -c "import openai; print('✅ OpenAI imported successfully')"

echo.
echo ✅ All tests passed! Virtual environment is working correctly.
echo You can now run RUN_APP.bat to start the application.
echo.
pause
""")
    
    print("✅ Portable application V2 created successfully!")
    print(f"📁 Location: {build_dir}")
    print("\n🎯 To use on target machine:")
    print("1. Copy the entire folder to the target computer")
    print("2. Make sure Python 3.8+ is installed on target computer")
    print("3. Run SETUP_VENV.bat (ONE-TIME setup)")
    print("4. Run RUN_APP.bat to start the application")
    print("\n📚 See HOW_TO_USE.txt for detailed instructions")
    
    return True

if __name__ == "__main__":
    success = create_portable_app()
    if success:
        print("\n🎉 Build completed successfully!")
    else:
        print("\n❌ Build failed!")
        sys.exit(1)
