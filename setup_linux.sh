#!/usr/bin/env bash
# ============================================================
# Forklift AI Safety System — Ubuntu Linux Deployment Script
# ============================================================
# Usage:
#   chmod +x setup_linux.sh
#   ./setup_linux.sh
#
# This script automates the full environment initialization
# on a fresh Ubuntu 20.04 / 22.04 / 24.04 system. It installs
# system-level graphics libraries, Python 3, pip, a virtual
# environment, and all project dependencies in sequence.
# ============================================================

set -e  # Exit immediately on any command failure

echo "============================================================"
echo " Forklift AI Safety System — Linux Deployment"
echo " Starting automated environment setup..."
echo "============================================================"
echo ""

# ----------------------------------------------------------
# STEP 1: System Package Update
# ----------------------------------------------------------
echo "[1/6] Updating system packages..."
sudo apt-get update -y
sudo apt-get upgrade -y
echo "       System packages updated."
echo ""

# ----------------------------------------------------------
# STEP 2: Install System-Level Graphics & Threading Libraries
# ----------------------------------------------------------
# These are CRITICAL for OpenCV and PyQt5 to function on Linux.
# Without them, you will encounter:
#   - ImportError: libGL.so.1: cannot open shared object file
#   - ImportError: libgthread-2.0.so.0: cannot open shared object file
#   - ImportError: libSM.so.6: cannot open shared object file
# ----------------------------------------------------------
echo "[2/6] Installing system-level graphics dependencies..."
sudo apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgthread-2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libfontconfig1 \
    libice6 \
    libxcb-xinerama0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxkbcommon-x11-0 \
    libdbus-1-3
echo "       Graphics dependencies installed."
echo ""

# ----------------------------------------------------------
# STEP 3: Install Python 3, pip, and venv
# ----------------------------------------------------------
echo "[3/6] Installing Python 3, pip, and venv..."
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev
echo "       Python 3 environment installed."
echo ""

# ----------------------------------------------------------
# STEP 4: Create Isolated Virtual Environment
# ----------------------------------------------------------
VENV_DIR="venv"
echo "[4/6] Creating Python virtual environment in ./${VENV_DIR}..."
if [ -d "$VENV_DIR" ]; then
    echo "       Existing venv found — removing stale environment..."
    rm -rf "$VENV_DIR"
fi
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
echo "       Virtual environment created and activated."
echo ""

# ----------------------------------------------------------
# STEP 5: Upgrade pip & Install Python Dependencies
# ----------------------------------------------------------
echo "[5/6] Installing Python dependencies from requirements.txt..."
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
echo "       All Python dependencies installed."
echo ""

# ----------------------------------------------------------
# STEP 6: Configure USB Serial Port Permissions
# ----------------------------------------------------------
# The RM04U relay board uses a CH340 USB-to-Serial chip.
# On Linux, serial ports (/dev/ttyUSB0, /dev/ttyACM0) require
# the user to be a member of the 'dialout' group.
# ----------------------------------------------------------
echo "[6/6] Configuring USB serial port permissions..."
CURRENT_USER=$(whoami)
if groups "$CURRENT_USER" | grep -q "\bdialout\b"; then
    echo "       User '$CURRENT_USER' is already in the 'dialout' group."
else
    echo "       Adding user '$CURRENT_USER' to the 'dialout' group..."
    sudo usermod -aG dialout "$CURRENT_USER"
    echo "       User added. NOTE: You must log out and log back in"
    echo "       (or reboot) for this change to take effect."
fi
echo ""

# ----------------------------------------------------------
# DEPLOYMENT COMPLETE
# ----------------------------------------------------------
echo "============================================================"
echo " DEPLOYMENT COMPLETE"
echo "============================================================"
echo ""
echo " To activate the environment in a new terminal session:"
echo "   source ${VENV_DIR}/bin/activate"
echo ""
echo " To launch the application:"
echo "   python3 ai_gui_system.py"
echo ""
echo " Serial port mapping (Linux equivalents):"
echo "   Windows COM3  ->  /dev/ttyUSB0"
echo "   Windows COM5  ->  /dev/ttyUSB1 (or /dev/ttyACM0)"
echo "   Run 'ls /dev/ttyUSB*' to discover connected devices."
echo ""
echo "============================================================"
