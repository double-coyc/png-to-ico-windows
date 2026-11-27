@echo off
chcp 65001 >nul

set "PYTHON_EXE=G:\Klishin\WinPython3.14dot\WPy64-314100\python\python.exe"
set "SCRIPT_DIR=C:\Users\student.IT-SA8\Downloads\png-to-ico-windows-main\png-to-ico-windows-main"

cd /d "%SCRIPT_DIR%"

if "%~1"=="" (
    "%PYTHON_EXE%" make_ico.py
) else (
    "%PYTHON_EXE%" make_ico.py --input "%~1"
)

pause
