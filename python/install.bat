@echo off
REM ============================================================
REM  install.bat - Setup script for sony-camera-control (Windows)
REM ============================================================
echo.
echo  Sony Camera Control - Python Setup
echo  ===================================
echo.

REM Check Python version
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+ from https://python.org
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Upgrade pip
python -m pip install --upgrade pip

REM Install the package in editable mode
echo Installing sony-camera-control...
pip install -e .

REM Install libusb backend for Windows
echo.
echo  NOTE: On Windows you also need the libusb DLL.
echo  The easiest way is to install libusb via:
echo    1. Download from https://github.com/libusb/libusb/releases
echo    2. Copy libusb-1.0.dll to your Python Scripts folder
echo  OR use Zadig (https://zadig.akeo.ie/) to install a WinUSB
echo  driver for your Sony camera.
echo.

echo.
echo  Installation complete!
echo  Activate the environment with:  .venv\Scripts\activate
echo  Then run:  python examples\basic_usage.py
echo.
