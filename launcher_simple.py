#!/usr/bin/env python3
"""
PDF to Presentation Converter - Simple Launcher
This script directly launches the Streamlit application without subprocess calls.
"""

import os
import sys
import time
import webbrowser
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
    
    try:
        # Import and run streamlit directly
        import streamlit.web.cli as stcli
        
        # Set up streamlit arguments
        sys.argv = [
            "streamlit", "run", str(app_file),
            "--server.port", "8501",
            "--server.address", "localhost",
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false"
        ]
        
        # Wait a moment for Streamlit to start
        time.sleep(2)
        
        # Open browser
        print("🌍 Opening browser...")
        webbrowser.open("http://localhost:8501")
        
        print("✅ Application is running!")
        print("📱 Open your browser and go to: http://localhost:8501")
        print("🔄 The application will automatically reload when you make changes.")
        print("⏹️  Press Ctrl+C to stop the application.")
        
        # Run streamlit
        stcli.main()
        
    except Exception as e:
        print(f"❌ Error starting application: {e}")
        print("Trying alternative method...")
        
        try:
            # Alternative: use subprocess with bundled Python
            import subprocess
            
            # Use the bundled Python executable
            if getattr(sys, 'frozen', False):
                python_exe = sys.executable
            else:
                python_exe = sys.executable
            
            process = subprocess.Popen([
                python_exe, "-m", "streamlit", "run", str(app_file),
                "--server.port", "8501",
                "--server.address", "localhost",
                "--server.headless", "true",
                "--browser.gatherUsageStats", "false"
            ])
            
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
                
        except Exception as e2:
            print(f"❌ Alternative method also failed: {e2}")
            input("Press Enter to exit...")

if __name__ == "__main__":
    main()
