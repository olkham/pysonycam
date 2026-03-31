#!/usr/bin/env bash
# ============================================================
#  install.sh - Setup script for sony-camera-control (Linux/macOS)
# ============================================================
set -e

echo ""
echo "  Sony Camera Control - Python Setup"
echo "  ==================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10+ first."
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "  macOS:         brew install python"
    exit 1
fi

# Install system dependencies for libusb (Linux only)
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "Installing system dependencies (libusb)..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq libusb-1.0-0 libusb-1.0-0-dev
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y libusb1 libusb1-devel
    elif command -v pacman &> /dev/null; then
        sudo pacman -Sy --noconfirm libusb
    else
        echo "WARNING: Could not detect package manager."
        echo "         Please install libusb-1.0 manually."
    fi
fi

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install in editable mode
echo "Installing sony-camera-control..."
pip install -e .

echo ""
echo "  Installation complete!"
echo "  Activate the environment with:  source .venv/bin/activate"
echo "  Then run:  python examples/basic_usage.py"
echo ""

# udev rules hint for Linux
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "  NOTE: To use USB without root on Linux, add a udev rule:"
    echo "    sudo tee /etc/udev/rules.d/99-sony-camera.rules << 'EOF'"
    echo '    SUBSYSTEM=="usb", ATTR{idVendor}=="054c", MODE="0666"'
    echo "    EOF"
    echo "    sudo udevadm control --reload-rules"
    echo "    sudo udevadm trigger"
    echo ""
fi
