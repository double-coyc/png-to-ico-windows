@echo off
chcp 65001 >nul

set "PYTHON_EXE=python"
set "SCRIPT_DIR=%~dp0"

cd /d "%SCRIPT_DIR%"

"%PYTHON_EXE%" -c "import PIL" 2>nul
if errorlevel 1 (
    echo Installing Pillow...
    "%PYTHON_EXE%" -m pip install Pillow
)

if "%~1"=="" (
    "%PYTHON_EXE%" make_ico.py
) else (
    "%PYTHON_EXE%" make_ico.py --input "%~1"
)

pause
