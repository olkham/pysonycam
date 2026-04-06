@echo off
REM ============================================================
REM  install.bat - Setup script for pysonycam (Windows)
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

REM Create virtual environment if it doesn't exist or is broken
if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    if exist ".venv" rmdir /s /q ".venv"
    python -m venv .venv
    if not exist ".venv\Scripts\activate.bat" (
        echo ERROR: Failed to create virtual environment.
        echo        Try: python -m pip install --upgrade pip
        echo        Then re-run this script.
        exit /b 1
    )
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Upgrade pip
python.exe -m pip install --upgrade pip

REM Install the package in editable mode
echo Installing pysonycam...
pip install -e .

REM WinUSB driver instructions
echo.
echo  IMPORTANT: You must replace the camera's driver with WinUSB using Zadig.
echo  Use Zadig v2.7 (newer versions may fail): https://github.com/pbatard/libwdi/releases/tag/v1.4.1
echo.
echo    1. Connect your Sony camera and set it to PC Remote mode
echo    2. Right-click zadig.exe and 'Run as administrator'
echo    3. In Zadig: Options ^> List All Devices
echo    4. Select your Sony camera from the dropdown (USB ID 054C)
echo    5. Set the target driver to 'WinUSB' and click 'Replace Driver'
echo.
echo  NOTE: This replaces the MTP driver. To restore it later:
echo        Device Manager ^> your camera ^> Update Driver ^> Search Automatically
echo.

echo.
echo  Installation complete!
echo  Activate the environment with:  .venv\Scripts\activate
echo  Then run:  python examples\basic_usage.py
echo.
