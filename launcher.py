#!/usr/bin/env python3
"""
PDF to Presentation Converter - Launcher
This script launches the Streamlit application and opens it in the default browser.
"""

import os
import sys
import subprocess
import time
import webbrowser
import threading
from pathlib import Path

def main():
    """Main launcher function"""
    print("🚀 Starting PDF to Presentation Converter...")
    print("📁 Working directory:", os.getcwd())
    
    # Check if .env file exists
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ Error: .env file not found!")
        print("Please make sure the .env file is in the same directory as this executable.")
        print("The .env file should contain your Azure OpenAI and Translator credentials.")
        input("Press Enter to exit...")
        return
    
    # Get the directory where the executable is located
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        app_dir = Path(sys._MEIPASS)
        app_file = app_dir / "app.py"
    else:
        # Running as script
        app_dir = Path(__file__).parent
        app_file = app_dir / "app.py"
    
    # Change to the app directory
    os.chdir(app_dir)
    
    # Set environment variables for Streamlit
    os.environ['STREAMLIT_SERVER_PORT'] = '8501'
    os.environ['STREAMLIT_SERVER_ADDRESS'] = 'localhost'
    os.environ['STREAMLIT_SERVER_HEADLESS'] = 'true'
    os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'
    
    print("🌐 Starting web interface...")
    
    # Start Streamlit in a subprocess
    try:
        # Use python -m streamlit run to ensure we use the correct Python environment
        process = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", str(app_file),
            "--server.port", "8501",
            "--server.address", "localhost",
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Wait a moment for Streamlit to start
        time.sleep(3)
        
        # Open browser
        print("🌍 Opening browser...")
        webbrowser.open("http://localhost:8501")
        
        print("✅ Application is running!")
        print("📱 Open your browser and go to: http://localhost:8501")
        print("🔄 The application will automatically reload when you make changes.")
        print("⏹️  Press Ctrl+C to stop the application.")
        
        # Keep the process running
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\n🛑 Stopping application...")
            process.terminate()
            process.wait()
            print("✅ Application stopped.")
            
    except Exception as e:
        print(f"❌ Error starting application: {e}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
