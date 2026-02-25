#!/usr/bin/env python3
"""
Python launcher for PDF to Presentation Converter
Uses the virtual environment created by SETUP_VENV.bat
"""

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
        print("\nApplication stopped by user.")
    except Exception as e:
        print(f"Error: {e}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
