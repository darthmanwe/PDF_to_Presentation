#!/usr/bin/env python3
"""
Portable Application Builder
Creates a self-contained folder with all dependencies for non-technical users.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

def create_portable_app():
    """Create a portable application folder"""
    
    print("🚀 Building Portable Application...")
    
    # Configuration
    app_name = "PDF_to_Presentation_Portable"
    source_dir = Path.cwd()
    build_dir = source_dir / "build" / app_name
    
    # Clean previous build
    if build_dir.exists():
        shutil.rmtree(build_dir)
    
    # Create build directory
    build_dir.mkdir(parents=True, exist_ok=True)
    
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
echo Starting PDF to Presentation Converter...
echo.
echo This application will open in your default web browser.
echo Please wait for the browser to open...
echo.
echo If the browser doesn't open automatically, go to: http://localhost:8501
echo.
echo Press Ctrl+C to stop the application when you're done.
echo.

REM Use ONLY the virtual environment's Python - NO system Python fallback
set VENV_PYTHON=%~dp0.venv\\Scripts\\python.exe
set VENV_STREAMLIT=%~dp0.venv\\Scripts\\streamlit.exe

REM Check if virtual environment Python exists
if not exist "%VENV_PYTHON%" (
    echo ERROR: Virtual environment Python not found!
    echo This folder is corrupted. Please re-download the application.
    pause
    exit /b 1
)

REM Check if streamlit is installed in venv
if not exist "%VENV_STREAMLIT%" (
    echo ERROR: Streamlit not found in virtual environment!
    echo This folder is corrupted. Please re-download the application.
    pause
    exit /b 1
)

echo Using Python from: %VENV_PYTHON%
echo Using Streamlit from: %VENV_STREAMLIT%
echo.

REM Run the application using ONLY the virtual environment
"%VENV_PYTHON%" -m streamlit run "%~dp0app.py" --server.port 8501 --server.headless true

pause
""")
    
    # Python launcher
    python_launcher = build_dir / "run_app.py"
    with open(python_launcher, 'w', encoding='utf-8') as f:
        f.write("""#!/usr/bin/env python3
\"\"\"
Python launcher for PDF to Presentation Converter
Uses ONLY the virtual environment's Python and Streamlit
NO system Python fallback
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
        print("This folder is corrupted. Please re-download the application.")
        input("Press Enter to exit...")
        return
    
    if not venv_streamlit.exists():
        print(f"ERROR: Streamlit not found in virtual environment at: {venv_streamlit}")
        print("This folder is corrupted. Please re-download the application.")
        input("Press Enter to exit...")
        return
    
    print(f"Using Python from: {venv_python}")
    print(f"Using Streamlit from: {venv_streamlit}")
    print()
    
    try:
        # Run Streamlit using ONLY the virtual environment's Python
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
    
    # Create virtual environment
    print("🐍 Creating virtual environment...")
    venv_dir = build_dir / ".venv"
    
    try:
        # Create virtual environment normally
        subprocess.run([
            sys.executable, "-m", "venv", str(venv_dir)
        ], check=True, capture_output=True)
        print("  ✅ Virtual environment created")
        
        # Create a clean pyvenv.cfg that won't have hardcoded paths
        pyvenv_cfg = venv_dir / "pyvenv.cfg"
        if pyvenv_cfg.exists():
            # Create a minimal, clean pyvenv.cfg
            clean_config = f"""home = .
include-system-site-packages = false
version = {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}
"""
            with open(pyvenv_cfg, 'w') as f:
                f.write(clean_config)
            
            print("  ✅ Created clean pyvenv.cfg without hardcoded paths")
            
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Failed to create virtual environment: {e}")
        return False
    
    # Install dependencies
    print("📦 Installing dependencies...")
    
    # Get pip path
    if os.name == 'nt':  # Windows
        pip_path = venv_dir / "Scripts" / "pip.exe"
        python_path = venv_dir / "Scripts" / "python.exe"
        activate_script = venv_dir / "Scripts" / "activate.bat"
    else:  # Unix/Linux
        pip_path = venv_dir / "bin" / "pip"
        python_path = venv_dir / "bin" / "python"
        activate_script = venv_dir / "bin" / "activate"
    
    try:
        # Use the virtual environment's Python to install packages
        if os.name == 'nt':  # Windows
            # Windows: Use the virtual environment's Python directly
            subprocess.run([
                str(python_path), "-m", "pip", "install", "--upgrade", "pip"
            ], check=True, capture_output=True)
            print("  ✅ Pip upgraded")
            
            subprocess.run([
                str(python_path), "-m", "pip", "install", "-r", str(build_dir / "requirements.txt")
            ], check=True, capture_output=True)
            print("  ✅ Dependencies installed")
        else:
            # Unix/Linux: Use the virtual environment's pip directly
            subprocess.run([
                str(pip_path), "install", "--upgrade", "pip"
            ], check=True, capture_output=True)
            print("  ✅ Pip upgraded")
            
            subprocess.run([
                str(pip_path), "install", "-r", str(build_dir / "requirements.txt")
            ], check=True, capture_output=True)
            print("  ✅ Dependencies installed")
        
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Failed to install dependencies: {e}")
        print(f"  🔍 Error output: {e.stderr.decode() if e.stderr else 'No error output'}")
        return False
    
    # Create user guide
    print("📚 Creating user guide...")
    user_guide = build_dir / "HOW_TO_USE.txt"
    with open(user_guide, 'w', encoding='utf-8') as f:
        f.write("""PDF TO PRESENTATION CONVERTER - PORTABLE VERSION
===============================================================

HOW TO USE:
===========

1. DOUBLE-CLICK "RUN_APP.bat" (Windows) or "run_app.py" (any OS)
   - This will start the application
   - A web browser will open automatically
   - If no browser opens, go to: http://localhost:8501

2. UPLOAD YOUR PDF:
   - Click "Browse files" to select your PDF
   - Choose language (English or Turkish)
   - Click "Convert PDF to Presentation"

3. DOWNLOAD YOUR PRESENTATION:
   - Wait for processing to complete
   - Click the download link for your .pptx file

4. TO STOP THE APPLICATION:
   - Press Ctrl+C in the command window
   - Or close the command window

TROUBLESHOOTING:
================

- If you get an error about missing .env file:
  Make sure the .env file is in the same folder as RUN_APP.bat

- If the browser doesn't open:
  Manually go to: http://localhost:8501

- If you get permission errors:
  Right-click RUN_APP.bat and "Run as administrator"

- If nothing happens when you double-click:
  Try right-click and "Open with" -> Python

FILES IN THIS FOLDER:
====================

- RUN_APP.bat: Windows launcher (double-click this!)
- run_app.py: Python launcher (alternative)
- app.py: Main application
- .env: Configuration file (keep this!)
- All other files: Application components

SUPPORT:
========

If you have issues, check that:
1. All files are in the same folder
2. The .env file contains your Azure API keys
3. You have an internet connection
4. Your antivirus isn't blocking the application

Happy converting!
""")
    
    # Create batch file for dependency installation (if needed)
    install_deps = build_dir / "INSTALL_DEPS.bat"
    with open(install_deps, 'w', encoding='utf-8') as f:
        f.write("""@echo off
echo Installing/Updating Dependencies...
echo.
echo This will install all required packages.
echo Please wait...
echo.
call .venv\\Scripts\\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Dependencies installed successfully!
echo You can now run RUN_APP.bat
pause
""")
    
    print("✅ Portable application created successfully!")
    print(f"📁 Location: {build_dir}")
    print("\n🎯 To use:")
    print("1. Copy the entire folder to any computer")
    print("2. Double-click RUN_APP.bat (Windows)")
    print("3. Or run: python run_app.py")
    print("\n📚 See HOW_TO_USE.txt for detailed instructions")
    
    return True

if __name__ == "__main__":
    success = create_portable_app()
    if success:
        print("\n🎉 Build completed successfully!")
    else:
        print("\n❌ Build failed!")
        sys.exit(1)
