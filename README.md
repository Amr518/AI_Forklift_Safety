# 🚜 AI Forklift Safety System (Limitless Future)

<p align="center">
  <img src="WhatsApp%20Image%202026-06-01%20at%203.48.05%20AM.jpeg" alt="AI Forklift Safety System UI" width="720" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
</p>

<p align="center">
  <strong>Industrial-Grade Real-Time AI Computer Vision Safety & Emergency Shutdown System</strong><br>
  <em>Designed for High-Risk Warehouse, Logistics, and Pharma 4.0 Industrial Environments</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Ubuntu%2024.04%20LTS-E95420?logo=ubuntu&logoColor=white" alt="Platform">
  <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/AI%20Model-Ultralytics%20YOLOv8-blue?logo=yolo" alt="YOLOv8">
  <img src="https://img.shields.io/badge/GUI-PyQt5%20Touch%20Kiosk-41CD52?logo=qt" alt="PyQt5">
  <img src="https://img.shields.io/badge/Hardware-RM04U%204--Channel%20USB%20Relay-FF6F00" alt="Hardware">
  <img src="https://img.shields.io/badge/IPC-Unix%20Domain%20Sockets%20(tmpfs)-00599C" alt="IPC">
  <img src="https://img.shields.io/badge/Standards-Pharma%204.0%20Compliant-success" alt="Pharma 4.0">
</p>

---

## 📌 Executive Summary

The **Limitless Future — AI Forklift Safety System** is a mission-critical, real-time safety monitoring solution designed to eliminate pedestrian-forklift collisions in high-density industrial plants and warehouses.

The system continuously processes up to **4 simultaneous industrial camera video streams** using an optimized **Ultralytics YOLOv8** deep learning model. When a person enters a designated **Region of Interest (ROI)** hazard zone, the system instantly triggers an industrial-grade **RM04U 4-Channel USB Relay**, executing hard shutdowns, activating sirens, or flashing emergency beacons within sub-millisecond latencies.

Built on **Ubuntu 24.04 LTS**, the architecture enforces complete process decoupling between the AI/GUI frontend and the hardware relay driver, guaranteeing uncompromised fail-safe operation even during camera disconnects, software restarts, or UI lockups.

---

## 🏗️ Core Architecture & Data Flow

The system employs a hardened **Two-Process Decoupled Architecture** connected via high-speed Unix Domain Sockets (`UDS`) mapped to Linux shared memory (`tmpfs`):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PROCESS 1: AI & GUI ENGINE                        │
│                           (ai_gui_system.py — User Space)                   │
│                                                                             │
│   ┌─────────────────────┐      ┌─────────────────────┐                      │
│   │ CameraWorkerThreads │      │    YoloDetector     │                      │
│   │ (4 Isolated Threads)│────► │    (YOLOv8 Nano)    │                      │
│   └──────────┬──────────┘      └──────────┬──────────┘                      │
│              │ (Raw Frames)               │ (Bounding Boxes)                │
│              ▼                            ▼                                 │
│   ┌──────────────────────────────────────────────────┐                      │
│   │   ROI Violation Engine (Normalized 0.0 to 1.0)   │                      │
│   └──────────────────────────┬───────────────────────┘                      │
│                              │                                              │
│                              ▼                                              │
│   ┌──────────────────────────────────────────────────┐                      │
│   │      USBRelayManager (IPC Client + Debounce)     │                      │
│   └──────────────────────────┬───────────────────────┘                      │
└──────────────────────────────┼──────────────────────────────────────────────┘
                               │ JSON-over-newline
                               ▼ Stream (/dev/shm/forklift_relay.sock)
┌─────────────────────────────────────────────────────────────────────────────┐
│                       PROCESS 2: HARDWARE WORKER DAEMON                     │
│                     (hardware_worker.py — Hardware Space)                   │
│                                                                             │
│   ┌──────────────────────────────────────────────────┐                      │
│   │   IPC Server (Thread-Safe Memory Ring Buffer)    │                      │
│   └──────────────────────────┬───────────────────────┘                      │
│                              │                                              │
│                              ▼                                              │
│   ┌──────────────────────────────────────────────────┐                      │
│   │   Pure Stateless Software OR-Gate (50ms Sweep)   │                      │
│   └──────────────────────────┬───────────────────────┘                      │
│                              │                                              │
│                              ▼ Serial Commands (CH340: 9600 Baud)           │
│   ┌──────────────────────────────────────────────────┐                      │
│   │      Edge-Triggered ASCII: N1..N4 (ON), F1..F4   │                      │
│   └──────────────────────────┬───────────────────────┘                      │
└──────────────────────────────┼──────────────────────────────────────────────┘
                               │ /dev/forklift_relay
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHYSICAL ACTUATION HARDWARE                         │
│                    RM04U 4-Channel Optocoupled USB Relay                    │
│                 [Ch 1: Horn]  [Ch 2: Siren]  [Ch 3: Beacon]  [Ch 4: E-Stop] │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ Key Industrial Engineering Features

### 1. 🛡️ Kernel-Level Physical USB Port Binding
- **Problem**: In industrial vehicles, mechanical vibrations frequently dislodge USB camera connectors. Linux kernel V4L2 then re-enumerates cameras randomly (e.g., swapping `/dev/video0` and `/dev/video2`), causing critical rear-blindspot cameras to swap with front-view cameras.
- **Solution**: The system resolves the physical motherboard USB bus topology (`sysfs`: `/sys/class/video4linux/videoX/device`) and binds each camera station to its immutable physical port path (e.g., `1-1.2`, `1-1.4`). Cameras will never swap, even across dynamic re-plugging or re-enumeration.

### 2. ⚡ Pure Stateless Software OR-Gate with Dual Relay Mapping
- The hardware daemon (`hardware_worker.py`) implements a zero-timer, pure boolean OR-gate logic cycle every 50 ms.
- **Dual Relay Assignments**: Each camera station can independently control two physical relay channels simultaneously (`Relay A` and `Relay B`), allowing dual action (e.g., strobe warning on Relay 1 AND emergency machine interlock on Relay 4).
- **Edge-Triggered Output**: ASCII commands (`N<ch>` / `F<ch>`) are dispatched strictly on genuine state transitions, avoiding serial buffer flooding.

### 3. 📊 Modular Health Diagnostics & Shift Reporting Engine
- **Health Diagnostics (`health_diagnostics.py`)**: Real-time monitoring of CPU, RAM, CPU Temperature, per-camera FPS, processing latency, and dropped frames.
- **Incident & Shift Reports (`report_manager.py` & `reporting_page.py`)**: Automatic generation of high-resolution PDF and TXT safety audit reports with embedded intrusion violation screenshots.
- **Automated Incident Emailing (`email_manager.py`)**: SMTP alerting service with local offline queue (`email_queue.json`) and retry persistence.
- **Automated Storage Management (`storage_manager.py`)**: Smart retention policies and monthly ZIP archiving of historical incident captures.

### 4. 📐 Normalized ROI Geometry (0.0 to 1.0)
- Region of Interest (hazard zone) coordinates are stored as floating-point ratios relative to frame dimensions:
  $$\text{norm\_x} = \frac{x}{W}, \quad \text{norm\_y} = \frac{y}{H}, \quad \text{norm\_w} = \frac{w}{W}, \quad \text{norm\_h} = \frac{h}{H}$$
- Eliminates bounding-box drift when changing resolutions, resizing windows, or running across displays from $800 \times 480$ embedded panels up to $3840 \times 2160$ 4K screens.

### 5. ⌨️ Bilingual Touchscreen Virtual Keyboard (AR / EN OSK)
- Purpose-built on-screen keyboard (`OSKWidget`) supporting **Arabic and English** layouts, Numeric keypad, and Symbols.
- Automatically hooks into text inputs, numerical spinboxes, and configuration dialogs via `TouchPasswordDialog` without stealing focus (`Qt.NoFocus`).

### 6. 🔐 5-Tier Role-Based Access Control (RBAC)
- **Operator (Level 1)**: Live monitoring, fullscreen viewing, manual channel activation.
- **Technician (Level 2)**: Diagnostics viewing, sensor verification.
- **Supervisor (Level 3)**: ROI calibration, camera assignment, relay mapping, report generation.
- **Engineer (Level 4)**: Baud rates, serial ports, YOLO confidence thresholds, model reload.
- **Administrator (Level 5)**: Software coil isolation, password management, system reset.
- Includes a 5-minute inactivity timer with automatic security fallback to Operator level.

### 7. 🔄 Resilient Systemd User Service & Auto-Recovery
- Self-healing systemd service (`forklift-ai.service`) with automatic 3-second recovery on failure (`Restart=always`).
- Includes a 15-second hardware stabilization delay at cold boot to ensure USB hubs and serial controllers enumerate completely before GUI initialization.

---

## 📁 Repository Structure

```text
AI_Forklift_Safety/
├── README.md                              # Main GitHub Documentation (English & Arabic)
├── PROJECT_DOCUMENTATION_AR.md            # Comprehensive Technical Reference (Arabic)
├── PROJECT_FULL_DOCUMENTATION.md          # Comprehensive Master Architecture Reference (English)
├── PROJECT_AUDIT_AND_BUGS_REFERENCE_AR.md # Defect Registry, Audit & Remediation Log
├── UBUNTU_MIGRATION_GUIDE.md              # Industrial Ubuntu 24.04 Deployment Guide
├── requirements.txt                       # Clean Python dependency manifest
├── .gitignore                             # Git ignore rules for clean repository
│
├── ai_gui_system.py                       # Main Qt5 HMI application, YOLO inference & video pipeline
├── hardware_worker.py                     # Standalone Hardware Daemon (Unix Socket + Dual Relay OR-Gate)
├── hardware_manager.py                    # IPC Client adapter, Debounce & Hold logic
├── health_diagnostics.py                  # System health, temperature, FPS & latency diagnostics engine
├── report_manager.py                      # PDF (ReportLab) and TXT shift report generator
├── reporting_page.py                      # HMI Reporting & Email management tab
├── email_manager.py                       # Automated incident email dispatcher with offline queue
├── storage_manager.py                     # Automated disk retention and monthly ZIP archiver
├── osk_widget.py                          # Industrial Bilingual (AR/EN) Virtual Touch Keyboard
├── detector.py                            # Ultralytics YOLOv8 object detection wrapper
├── roi.py                                 # Normalized Region of Interest math & interactive label
├── camera.py                              # V4L2 OpenCV video capture abstraction
├── security.py                            # 5-Tier Role-based access control (RBAC) & hashing
│
├── start_system.sh                        # Multi-process orchestrator & startup manager
├── setup_usb.sh                           # Udev rules installer for persistent /dev/forklift_relay
├── setup_linux.sh                         # Linux environment & dependencies installer
├── forklift-ai.service                    # Systemd user-space service unit definition
├── AI_Forklift_System.desktop             # Desktop launcher shortcut
│
├── config.json                            # System configurations (ROIs, relays, USB ports, thresholds)
├── security.json                          # RBAC credentials & role definition store
├── yolov8n.pt                             # Pre-trained YOLOv8 Nano model weights
│
├── test_or_gate_logic.py                  # Unit tests: 16 Test Cases + 10,000-cycle stress test
├── scratch/                               # Automated verification suites
│   ├── test_physical_usb_binding.py       # USB Hub topology binding tests (9/9 PASS)
│   ├── test_roi_and_layout_stability.py   # ROI scaling and layout tests (5/5 PASS)
│   ├── test_multi_resolution_adaptation.py# Multi-resolution adaptation tests (9/9 PASS)
│   └── test_card_relay_and_camera_dropdown.py # Dropdown & relay UI tests (4/4 PASS)
└── forklift_ai_safety/                    # Historical modular package reference
```

---

## 🚀 Quick Start & Installation

### 1. System Dependencies (Ubuntu 24.04 LTS)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git \
    libgl1-mesa-glx libglib2.0-0 libxcb-xinerama0 libegl1-mesa libxkbcommon-x11-0
```

### 2. Clone Repository & Setup Virtual Environment

```bash
git clone https://github.com/<YOUR_ORGANIZATION>/AI_Forklift_Safety.git
cd AI_Forklift_Safety

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python requirements
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Hardware Permissions & Udev Rules

Grant your Linux user serial dialout permissions and configure persistent symlinks for the RM04U relay board:

```bash
# Add user to dialout group
sudo usermod -aG dialout $USER

# Install udev rule for /dev/forklift_relay
chmod +x setup_usb.sh
./setup_usb.sh
```

*(Note: Log out and log back in, or reboot, for group permissions to take effect).*

---

## 🚦 System Execution

### Option A: Standard Startup Script (Recommended)
```bash
chmod +x start_system.sh
./start_system.sh              # 15s USB stabilization countdown
./start_system.sh --no-delay   # Developer instant launch
```

### Option B: Systemd Monitored Service (Production Kiosk)
```bash
# Enable and start user service
mkdir -p ~/.config/systemd/user
cp forklift-ai.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now forklift-ai.service

# View live operational logs
journalctl --user -u forklift-ai.service -f
```

---

## 🧪 Automated Testing & Verification

All tests run headless and do not require physical hardware to be connected:

```bash
source venv/bin/activate

# 1. Pure OR-Gate Logic & Sub-Millisecond Stress Latency Test (13/13 PASS)
python3 test_or_gate_logic.py -v

# 2. Kernel Physical USB Hub Topology Binding Test (9/9 PASS)
python3 scratch/test_physical_usb_binding.py -v

# 3. Dynamic Resolution Scaling (800x480 to 4K UHD) Test (9/9 PASS)
python3 scratch/test_multi_resolution_adaptation.py

# 4. Normalized ROI Geometry & Grid Decoupling Test (5/5 PASS)
python3 scratch/test_roi_and_layout_stability.py
```

---

## 🛠️ Defect Remediation & Hardening Log

During the production hardening phase (September 2026), all identified defects and race conditions were systematically resolved:

| ID | Issue Description | Severity | Status |
|:---:|---|:---:|:---:|
| **3.1** | YOLO inference and blink timers trapped inside `on_physical_path_discovered` | 🔴 Critical | ✅ **RESOLVED** (Relocated to `start_camera()`) |
| **3.2** | Fatal crash on saving YOLO model due to `model_name` vs `model_path` kwargs | 🔴 Critical | ✅ **RESOLVED** (Defensive kwargs in `detector.py`) |
| **3.3** | Potential `AttributeError` due to uninitialized `manual_overrides` | 🟠 High | ✅ **RESOLVED** (Initialized in `hardware_manager.py`) |
| **3.4** | Incomplete serial reconnection on runtime baud change | 🟠 High | ✅ **RESOLVED** (Service restart guidance & IPC sync) |
| **3.5** | High CPU & journal disk spam by OpenCV C++ V4L2 warnings | 🟡 Medium | ✅ **RESOLVED** (`cv2.setLogLevel(0)` & silent logging) |
| **3.6** | Camera feed offline displayed false "Path Violation" alarm | 🟡 Medium | ✅ **RESOLVED** (Differentiated feed offline banner) |
| **3.7** | Desynchronized auto-reset timer text in audit logs | 🟡 Medium | ✅ **RESOLVED** (Dynamic reading from `alarm_auto_reset`) |
| **3.8** | UI freeze when closing cameras in `pause_all_card_timers` | 🟡 Medium | ✅ **RESOLVED** (Bounded non-blocking worker thread wait) |

---

## 📄 License & Intellectual Property

Copyright © 2026 **Limitless Future Technologies**. All rights reserved.  
Engineered for Pharma 4.0 Industrial Safety Standards.
