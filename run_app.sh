#!/bin/bash

echo "Starting PDF to Presentation Converter..."
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    echo "Please install Python 3.8+ and try again"
    exit 1
fi

# Check if requirements are installed
echo "Checking dependencies..."
if ! python3 -c "import streamlit" &> /dev/null; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install dependencies"
        exit 1
    fi
fi

# Run the application
echo "Starting Streamlit application..."
echo
echo "The application will open in your default browser."
echo "If it doesn't open automatically, go to: http://localhost:8501"
echo
echo "Press Ctrl+C to stop the application"
echo

streamlit run app.py
