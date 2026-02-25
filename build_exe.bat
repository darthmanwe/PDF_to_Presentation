@echo off
echo ========================================
echo Building PDF to Presentation Converter
echo ========================================
echo.

echo Installing PyInstaller...
pip install pyinstaller==6.3.0

echo.
echo Building executable...
pyinstaller --clean pdf_to_presentation.spec

echo.
echo ========================================
echo Build completed!
echo ========================================
echo.
echo The executable is located in: dist\PDF_to_Presentation_Converter.exe
echo.
echo To distribute to your father:
echo 1. Copy the .exe file from the dist folder
echo 2. Copy the .env file (with your Azure credentials)
echo 3. Put both files in the same folder
echo 4. Double-click the .exe to run
echo.
pause
