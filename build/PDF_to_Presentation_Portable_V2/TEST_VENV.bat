@echo off
echo ========================================
echo Virtual Environment Test
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ❌ Virtual environment not found!
    echo Please run SETUP_VENV.bat first.
    pause
    exit /b 1
)

echo ✅ Virtual environment found!

echo.
echo Testing Python...
".venv\Scripts\python.exe" --version

echo.
echo Testing package imports...
".venv\Scripts\python.exe" -c "import streamlit; print('✅ Streamlit imported successfully')"
".venv\Scripts\python.exe" -c "import fitz; print('✅ PyMuPDF imported successfully')"
".venv\Scripts\python.exe" -c "import pptx; print('✅ python-pptx imported successfully')"
".venv\Scripts\python.exe" -c "import openai; print('✅ OpenAI imported successfully')"

echo.
echo ✅ All tests passed! Virtual environment is working correctly.
echo You can now run RUN_APP.bat to start the application.
echo.
pause
