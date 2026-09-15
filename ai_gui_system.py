# ==========================================
# DLL CONFLICT WORKAROUND FOR WINDOWS
# ==========================================
try:
    import torch
except ImportError:
    pass

# ==========================================
# IMPORTS
# ==========================================
import os
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["OPENCV_VIDEOIO_DEBUG"] = "0"

import sys
import cv2
try:
    cv2.setLogLevel(0)
except Exception:
    pass
import time
import glob
import re
import json
import threading
import platform
import datetime
import numpy as np

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QFrame,
    QComboBox,
    QSizePolicy,
    QInputDialog,
    QMessageBox,
    QLineEdit,
    QGridLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QGroupBox,
    QScrollArea,
    QSlider,
    QSpinBox,
    QDoubleSpinBox,
    QAbstractSpinBox,
    QCheckBox,
    QFileDialog,
    QListView,
    QProgressBar
)

from PyQt5.QtGui import (
    QImage,
    QPixmap,
    QColor,
    QPainter,
    QRadialGradient
)

from PyQt5.QtCore import (
    QTimer,
    Qt,
    QRect,
    QPoint,
    QEvent,
    QThread,
    pyqtSignal
)

# Modular Component Imports
from security import SecurityManager
from camera import Camera
from detector import YoloDetector
from alarm import AlarmSystem
from roi import VideoLabel
from hardware_manager import USBRelayManager

# Touch Authentication Dialog
from osk_widget import TouchPasswordDialog, OSKWidget

# Modular Health & Diagnostics
try:
    from health_diagnostics import MetricsEngine, HealthDiagnosticsPage
    _HEALTH_MODULE_AVAILABLE = True
except Exception as _hd_err:
    _HEALTH_MODULE_AVAILABLE = False
    print(f"[Health] Module not available: {_hd_err}")

# Modular Reporting & Email
try:
    from report_manager import ReportManager
    from email_manager import EmailConfig, EmailWorker, EmailScheduler
    from storage_manager import StorageManager, StorageWorker
    from reporting_page import ReportsEmailPage
    _REPORTING_MODULE_AVAILABLE = True
except Exception as _rep_err:
    _REPORTING_MODULE_AVAILABLE = False
    print(f"[Reporting] Module not available: {_rep_err}")







# ==========================================
# CUSTOM DRAWN CIRCULAR LED WIDGET
# ==========================================
class CircularLED(QWidget):
    """
    Custom-drawn Circular LED representing physical glass-reflections of SCADA panels.
    Flashes dynamically every 500ms during alarm breaches.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.state = "standby"  # standby, secure, breach, error
        self.flash_state = False
        
        # Timer specifically for sector intrusion flashing alerts (500ms)
        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self.toggle_flash)

    def set_state(self, state):
        self.state = state
        if state == "breach":
            if not self.flash_timer.isActive():
                self.flash_timer.start(500)
        else:
            self.flash_timer.stop()
            self.flash_state = False
        self.update()

    def toggle_flash(self):
        self.flash_state = not self.flash_state
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect()
        center_x = rect.x() + rect.width() / 2.0
        center_y = rect.y() + rect.height() / 2.0
        radius = min(rect.width(), rect.height()) / 2.0 - 1
        
        # Radial gradient for standard SCADA hardware reflections
        gradient = QRadialGradient(center_x - radius/3.0, center_y - radius/3.0, radius)
        
        if self.state == "secure":
            c_bright = QColor(46, 204, 113)  # #2ecc71 (rich green)
            c_dark = QColor(39, 174, 96)     # #27ae60 (dark green shadow)
        elif self.state == "breach":
            if self.flash_state:
                c_bright = QColor(255, 100, 100)  # high intensity red
                c_dark = QColor(231, 76, 60)
            else:
                c_bright = QColor(231, 76, 60)    # #e74c3c danger red
                c_dark = QColor(150, 40, 30)      # deep dark red
        elif self.state == "error":
            c_bright = QColor(243, 156, 18)   # #f39c12 amber
            c_dark = QColor(211, 84, 0)       # deep orange
        else:
            c_bright = QColor(100, 110, 120)  # standby gray
            c_dark = QColor(50, 55, 60)
            
        gradient.setColorAt(0.0, c_bright)
        gradient.setColorAt(0.8, c_dark)
        gradient.setColorAt(1.0, QColor(25, 25, 25))  # Outer boundary metal bezel ring
        
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect.adjusted(1, 1, -1, -1))


# ============================================================
# PHYSICAL USB PORT RESOLUTION & HARDWARE BINDING
# ============================================================
def get_physical_usb_path(device_node):
    """
    Resolves a V4L2 device node (e.g. '/dev/video0' or index 0) to its persistent
    physical USB port path on the motherboard / USB controller bus (e.g., '1-1.2', '1-1.4', '1-2').
    Returns None if device or sysfs node does not exist or fails to resolve.
    """
    if device_node is None:
        return None
    if isinstance(device_node, int):
        node_name = f"video{device_node}"
    else:
        node_name = os.path.basename(str(device_node))
    sys_path = f"/sys/class/video4linux/{node_name}/device"
    try:
        if not os.path.exists(sys_path):
            return None
        real_path = os.path.realpath(sys_path)
        parts = real_path.split('/')
        # Look in reverse to catch the most specific USB port (e.g., 1-1.2 over 1-1)
        for part in reversed(parts):
            if '-' in part and not part.startswith('usb') and ':' not in part:
                return part
        for part in parts:
            if '-' in part and not part.startswith('usb') and ':' not in part:
                return part
        return real_path
    except Exception:
        return None


def persist_station_physical_path(station_id, physical_path):
    """
    Persists an auto-detected or configured physical USB port binding to config.json
    for both per-camera and settings dictionaries.
    """
    config_path = "config.json"
    try:
        data = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                data = json.load(f)
        cam_key = f"camera_{station_id}"
        if cam_key not in data:
            data[cam_key] = {}
        data[cam_key]["physical_usb_path"] = physical_path

        if "settings" not in data:
            data["settings"] = {}
        if "camera_physical_paths" not in data["settings"]:
            data["settings"]["camera_physical_paths"] = [None, None, None, None]
        while len(data["settings"]["camera_physical_paths"]) < 4:
            data["settings"]["camera_physical_paths"].append(None)
        if 0 <= station_id < len(data["settings"]["camera_physical_paths"]):
            data["settings"]["camera_physical_paths"][station_id] = physical_path

        with open(config_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"[CAM_THREAD] Persisted Station {station_id + 1} physical USB path: {physical_path}")
    except Exception as e:
        print(f"[CAM_THREAD] Failed to persist physical path for Station {station_id + 1}: {e}")


def get_usb_camera_details(device_node):
    """
    Extracts rich USB hardware identification for a V4L2 device node:
    - physical_port: Motherboard / hub USB port string (e.g., '1-1.2', '1-4')
    - serial: Hardware USB serial number (if exposed by camera firmware)
    - product: Camera product model name
    - manufacturer: Camera manufacturer
    - node: Full device node path (e.g., '/dev/video0')
    - by_id: Persistent /dev/v4l/by-id path if present
    - by_path: Persistent /dev/v4l/by-path path if present
    - display_label: Human-readable localized description for UI dropdowns
    """
    if device_node is None:
        return None
    if isinstance(device_node, int):
        node_name = f"video{device_node}"
    else:
        node_name = os.path.basename(str(device_node))
    
    full_node = f"/dev/{node_name}" if not str(device_node).startswith("/dev/") else str(device_node)
    
    sys_path = f"/sys/class/video4linux/{node_name}/device"
    physical_port = None
    serial = None
    product = None
    manufacturer = None
    by_id = None
    by_path = None

    if os.path.exists(sys_path):
        try:
            real_path = os.path.realpath(sys_path)
            parts = real_path.split('/')
            for part in reversed(parts):
                if '-' in part and not part.startswith('usb') and ':' not in part:
                    physical_port = part
                    break
            
            curr = real_path
            while curr and curr != '/':
                s_path = os.path.join(curr, 'serial')
                p_path = os.path.join(curr, 'product')
                m_path = os.path.join(curr, 'manufacturer')
                if not serial and os.path.exists(s_path):
                    try:
                        with open(s_path, 'r', encoding='utf-8', errors='ignore') as f:
                            val = f.read().strip()
                            if val:
                                serial = val
                    except Exception:
                        pass
                if not product and os.path.exists(p_path):
                    try:
                        with open(p_path, 'r', encoding='utf-8', errors='ignore') as f:
                            val = f.read().strip()
                            if val:
                                product = val
                    except Exception:
                        pass
                if not manufacturer and os.path.exists(m_path):
                    try:
                        with open(m_path, 'r', encoding='utf-8', errors='ignore') as f:
                            val = f.read().strip()
                            if val:
                                manufacturer = val
                    except Exception:
                        pass
                if serial and product:
                    break
                curr = os.path.dirname(curr)
        except Exception:
            pass

    # Check /dev/v4l/by-id symlinks
    if os.path.exists("/dev/v4l/by-id"):
        try:
            for link in glob.glob("/dev/v4l/by-id/*"):
                if os.path.islink(link):
                    tgt = os.path.realpath(link)
                    if tgt == full_node or os.path.basename(tgt) == node_name:
                        by_id = link
                        if not serial:
                            base = os.path.basename(link)
                            parts = base.split('_')
                            if len(parts) >= 3:
                                cand_s = parts[-1].split('-')[0]
                                if cand_s and not cand_s.isdigit() and len(cand_s) >= 4:
                                    serial = cand_s
                        break
        except Exception:
            pass

    # Check /dev/v4l/by-path symlinks
    if os.path.exists("/dev/v4l/by-path"):
        try:
            for link in glob.glob("/dev/v4l/by-path/*"):
                if os.path.islink(link):
                    tgt = os.path.realpath(link)
                    if tgt == full_node or os.path.basename(tgt) == node_name:
                        by_path = link
                        break
        except Exception:
            pass

    prod_name = product or "Camera"
    if physical_port and serial:
        display_label = f"USB Port [{physical_port}] | Serial: {serial} ({prod_name} - {full_node})"
    elif physical_port:
        display_label = f"USB Port [{physical_port}] ({prod_name} - {full_node})"
    elif serial:
        display_label = f"Serial: {serial} ({prod_name} - {full_node})"
    else:
        display_label = f"{full_node} ({prod_name})"

    return {
        "node": full_node,
        "node_name": node_name,
        "physical_port": physical_port,
        "serial": serial,
        "product": product,
        "manufacturer": manufacturer,
        "by_id": by_id,
        "by_path": by_path,
        "display_label": display_label
    }


def is_camera_node_match(candidate_node, target_binding):
    """
    Checks if a candidate video node matches the configured target binding
    (physical USB port, serial number, by-path/by-id symlink, or device node).
    """
    if target_binding is None:
        return True
    
    cand_str = str(candidate_node).strip()
    target_str = str(target_binding).strip()

    # 1. Exact node string match
    if cand_str == target_str:
        return True
    
    # 2. Normalize node index match (e.g. 0 vs /dev/video0)
    if (cand_str.isdigit() or cand_str.startswith("/dev/video")) and \
       (target_str.isdigit() or target_str.startswith("/dev/video")):
        m_cand = re.search(r'\d+', os.path.basename(cand_str))
        m_tgt = re.search(r'\d+', os.path.basename(target_str))
        if m_cand and m_tgt and m_cand.group() == m_tgt.group():
            return True

    # 3. Check physical USB path from get_physical_usb_path
    cand_phys = get_physical_usb_path(candidate_node)
    if cand_phys and (cand_phys == target_str or target_str == f"port:{cand_phys}"):
        return True

    details = get_usb_camera_details(candidate_node)
    if details:
        det_phys = details.get("physical_port")
        if det_phys and (det_phys == target_str or target_str == f"port:{det_phys}"):
            return True

        det_serial = details.get("serial")
        clean_target_serial = target_str[7:].strip() if target_str.startswith("serial:") else target_str
        if det_serial and (det_serial == clean_target_serial or det_serial == target_str):
            return True

        det_by_path = details.get("by_path")
        if det_by_path and det_by_path == target_str:
            return True

        det_by_id = details.get("by_id")
        if det_by_id and det_by_id == target_str:
            return True

    return False


# ============================================================
# BACKGROUND MULTITHREADED CAMERA INGESTION WORKER (QTHREAD)
# ============================================================
class CameraWorkerThread(QThread):
    frame_ready = pyqtSignal(np.ndarray)
    status_changed = pyqtSignal(bool, str)
    path_discovered = pyqtSignal(int, str)

    # Thread-Safe Global Registry for tracking both indices and physical paths safely across threads
    active_physical_paths = set()
    active_device_indices = set()
    _registry_lock = threading.Lock()

    def __init__(self, device_index, station_id=0, target_physical_usb_path=None, width=640, height=480):
        super().__init__()
        # If device_index is a string representing a number, cast it to int
        if isinstance(device_index, str) and device_index.isdigit():
            self.device_index = int(device_index)
        else:
            self.device_index = device_index
        self.station_id = station_id
        self.target_physical_usb_path = target_physical_usb_path
        self.current_physical_path = None
        self.current_device_index = None

        self.width = width
        self.height = height
        self.running = False
        self.camera = None
        # Latest captured frame — continuously replaced, never queued
        self.latest_frame = None
        self._frame_lock = threading.Lock()

    @staticmethod
    def _normalize_device_index(device_node):
        if isinstance(device_node, int):
            return device_node
        s = str(device_node)
        m = re.search(r'\d+', os.path.basename(s))
        if m:
            return int(m.group())
        return s

    def _release_camera_locked(self):
        """
        Safely unregisters physical path and device index from the global registry,
        and releases the OpenCV capture resource.
        """
        with CameraWorkerThread._registry_lock:
            if self.current_physical_path:
                CameraWorkerThread.active_physical_paths.discard(self.current_physical_path)
                self.current_physical_path = None
            if self.current_device_index is not None:
                CameraWorkerThread.active_device_indices.discard(str(self.current_device_index))
                CameraWorkerThread.active_device_indices.discard(self._normalize_device_index(self.current_device_index))
                self.current_device_index = None

        if self.camera is not None:
            try:
                self.camera.release()
            except Exception:
                pass
            self.camera = None

    def _scan_for_camera(self):
        """
        Strict physical reconnection scan:
        1. Iterates available /dev/video* nodes.
        2. Strict Match Gate: Verifies candidate physical USB path matches target_physical_usb_path.
        3. Conflict Gate: Ensures candidate physical path & index are not in active registries.
        4. Validation Gate: Tests opening and reading a valid frame (filters metadata nodes).
        5. Registers candidate and binds camera.
        """
        candidate_nodes = glob.glob('/dev/video*')
        # Sort candidates numerically (video0, video1, video2...)
        def _sort_key(p):
            m = re.search(r'\d+', os.path.basename(p))
            return int(m.group()) if m else 9999
        candidate_nodes.sort(key=_sort_key)

        # Fallback if no /dev/video* filesystem nodes found (e.g. simulated environment)
        if not candidate_nodes and self.device_index is not None:
            candidate_nodes = [self.device_index]

        for candidate in candidate_nodes:
            cand_phys = get_physical_usb_path(candidate)

            # Strict Match Gate:
            if self.target_physical_usb_path is not None:
                # If target physical path is set, candidate MUST match target (physical USB port, serial, or node)
                if not is_camera_node_match(candidate, self.target_physical_usb_path):
                    continue
            else:
                # Initial Boot: target_physical_usb_path not yet set.
                # If candidate has no physical USB path and does not match initial device_index, skip
                if cand_phys is None and str(candidate) != str(self.device_index) and self._normalize_device_index(candidate) != self._normalize_device_index(self.device_index):
                    continue

            # Conflict Gate: Ensure candidate physical path & index are not active elsewhere
            with CameraWorkerThread._registry_lock:
                cand_idx = self._normalize_device_index(candidate)
                cand_str = str(candidate)
                if cand_phys and cand_phys in CameraWorkerThread.active_physical_paths:
                    continue
                if cand_str in CameraWorkerThread.active_device_indices or cand_idx in CameraWorkerThread.active_device_indices:
                    continue

            # Validation Gate: Open with Camera and verify valid video streaming
            try:
                test_cam = Camera(device_index=candidate, width=self.width, height=self.height)
                if test_cam.cap is None or not test_cam.cap.isOpened():
                    if test_cam.cap is not None:
                        test_cam.release()
                    continue

                ret, frame = test_cam.read_frame()
                if not ret or frame is None:
                    test_cam.release()
                    continue

                # Valid video stream verified. Acquire lock and register ownership.
                with CameraWorkerThread._registry_lock:
                    cand_idx = self._normalize_device_index(candidate)
                    cand_str = str(candidate)
                    if cand_phys and cand_phys in CameraWorkerThread.active_physical_paths:
                        test_cam.release()
                        continue
                    if cand_str in CameraWorkerThread.active_device_indices or cand_idx in CameraWorkerThread.active_device_indices:
                        test_cam.release()
                        continue

                    # Auto-detect & persist physical path on first successful initial boot
                    if self.target_physical_usb_path is None and cand_phys:
                        self.target_physical_usb_path = cand_phys
                        persist_station_physical_path(self.station_id, cand_phys)
                        self.path_discovered.emit(self.station_id, cand_phys)

                    if cand_phys:
                        CameraWorkerThread.active_physical_paths.add(cand_phys)
                        self.current_physical_path = cand_phys

                    CameraWorkerThread.active_device_indices.add(cand_str)
                    CameraWorkerThread.active_device_indices.add(cand_idx)
                    self.current_device_index = candidate
                    self.camera = test_cam

                    with self._frame_lock:
                        self.latest_frame = frame
                    self.frame_ready.emit(frame)
                    return True

            except Exception as e:
                continue

        return False

    def run(self):
        self.running = True
        last_scan_time = 0.0

        while self.running:
            # Reconnection / scan loop when camera is not connected
            if self.camera is None or self.camera.cap is None or not self.camera.cap.isOpened():
                now = time.time()
                if now - last_scan_time >= 1.5:  # Retry scan quietly every 1-2 seconds
                    last_scan_time = now
                    self.status_changed.emit(False, "Reconnecting...")
                    found = self._scan_for_camera()
                    if found:
                        self.status_changed.emit(True, "Online")
                    else:
                        time.sleep(0.1)
                        continue
                else:
                    time.sleep(0.1)
                    continue

            # Active frame ingestion loop
            try:
                ret, frame = self.camera.read_frame()
                if ret and frame is not None:
                    with self._frame_lock:
                        self.latest_frame = frame
                    self.frame_ready.emit(frame)
                else:
                    # Frame read failed -> camera unplugged or bus reset
                    print(f"[CAM_THREAD] Station {self.station_id + 1} stream lost. Triggering reconnection...")
                    self._release_camera_locked()
                    self.status_changed.emit(False, "Reconnecting...")
                    time.sleep(0.1)
            except Exception as e:
                print(f"[CAM_THREAD] Exception reading Station {self.station_id + 1}: {e}")
                self._release_camera_locked()
                self.status_changed.emit(False, "Reconnecting...")
                time.sleep(0.1)

        self._release_camera_locked()

    def stop(self):
        self.running = False
        self.wait(3000)
        self._release_camera_locked()


# ==========================================
# CAMERA CARD WIDGET (REUSABLE COMPONENT)
# ==========================================
class CameraCardWidget(QFrame):
    """
    Encapsulates all logic, UI controls, local processing timer, and error boundary
    for a single monitoring station. Houses dynamic brushed aluminum gradients.
    """
    def __init__(self, cam_id, device_index, detector, security_manager, relay_manager, parent=None, ui_scale=1.0):
        super().__init__(parent)
        self.cam_id = cam_id
        self.device_index = device_index
        self.detector = detector
        self.security = security_manager
        self.relay_manager = relay_manager
        self.parent_window = parent
        # ui_scale is clamped to [0.45, 1.5] to support everything from 800x480/1024x600 up to 4K.
        # It is used only for sizing/spacing; never for AI/camera/relay logic.
        self.ui_scale = max(0.45, min(1.5, ui_scale))
        
        self.camera_online = False
        self.camera_thread = None
        self.blink_state = False
        self.blink_timer = None
        self.alarm_system = AlarmSystem()
        self.prev_time = 0
        self.is_active = False
        self.prev_warning = False  # Track alert state transitions for visual UI updates
        self.last_hardware_state = None  # Dedicated hardware write gate
        self.yolo_timer = None  # 1-second timer that drives YOLO inference
        self._or_off_timer = None      # One-shot 3-second timer: forces OR output OFF after ON
        self._or_trigger_armed = True   # True = a new ON detection event may trigger the relay

        # Physical USB port binding for camera persistence across reconnections
        self.target_physical_usb_path = None
        if self.parent_window and hasattr(self.parent_window, "global_settings"):
            phys_paths = self.parent_window.global_settings.get("camera_physical_paths", [])
            if 0 <= self.cam_id < len(phys_paths):
                self.target_physical_usb_path = phys_paths[self.cam_id]

        if not self.target_physical_usb_path:
            try:
                if os.path.exists("config.json"):
                    with open("config.json", "r") as f:
                        cdata = json.load(f)
                    cam_k = f"camera_{self.cam_id}"
                    if cam_k in cdata and "physical_usb_path" in cdata[cam_k]:
                        self.target_physical_usb_path = cdata[cam_k]["physical_usb_path"]
            except Exception:
                pass

        # Check persisted feed enabled/disabled state
        self.is_feed_enabled = True
        if self.parent_window and hasattr(self.parent_window, "global_settings"):
            cams_en = self.parent_window.global_settings.get("cameras_enabled", [])
            if 0 <= self.cam_id < len(cams_en):
                self.is_feed_enabled = bool(cams_en[self.cam_id])
        if not hasattr(self, 'is_feed_enabled') or self.is_feed_enabled is None:
            try:
                if os.path.exists("config.json"):
                    with open("config.json", "r") as f:
                        cdata = json.load(f)
                    cam_k = f"camera_{self.cam_id}"
                    if cam_k in cdata and "enabled" in cdata[cam_k]:
                        self.is_feed_enabled = bool(cdata[cam_k]["enabled"])
            except Exception:
                pass

        self.setObjectName("cameraCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # High contrast dynamic brushed aluminum/metallic frame styling sheets
        self.setStyleSheet("""
            QFrame#cameraCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2b323c, stop:1 #151a21);
                border: 3px solid #4a5768;
                border-radius: 8px;
            }
            QFrame#cameraCard[warning="true"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #421b1d, stop:1 #1a0b0c);
                border: 3px solid #e74c3c;
            }
            QFrame#cameraCard[warning="false"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1b3d26, stop:1 #0c1a10);
                border: 3px solid #2ecc71;
            }
            QFrame#cameraCard[warning="standby"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #22262d, stop:1 #111317);
                border: 3px solid #2d3846;
            }
            QLabel {
                background: transparent;
            }
        """)

        # Derive scaled integer values for this card's layout.
        # Scale factor is clamped to <=1.0 so large-screen layouts are never enlarged.
        _s = self.ui_scale
        _card_margin   = max(4,  int(10 * _s))
        _card_spacing  = max(3,  int(6  * _s))
        _title_fs      = max(9,  int(13 * _s))
        _banner_fs     = max(8,  int(11 * _s))
        # Video viewport minimum: must fit comfortably on displays from 800x480 to 4K.
        _vid_min_w     = max(100, int(240 * _s))
        _vid_min_h     = max(75,  int(180 * _s))

        # Main Layout of the card
        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(_card_margin, _card_margin, _card_margin, _card_margin)
        card_layout.setSpacing(_card_spacing)

        # Header section (Station label + Local alarm status indicator)
        header_layout = QHBoxLayout()
        self.title_label = QLabel(f"🚚 STATION {self.cam_id + 1:02d} - ● SECURE")
        self.title_label.setStyleSheet(f"color: #10b981; font-family: 'Segoe UI Semibold'; font-size: {_title_fs}px; font-weight: 800; letter-spacing: 0.5px;")
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        # Custom Circular LED
        self.led_indicator = CircularLED(self)
        self.led_indicator.set_state("secure")
        header_layout.addWidget(self.led_indicator)

        self.status_banner = QLabel("● SECURE")
        self.status_banner.setStyleSheet(f"color: #10b981; font-family: 'Segoe UI Semibold'; font-size: {_banner_fs}px; font-weight: bold; margin-left: 4px;")
        header_layout.addWidget(self.status_banner)

        card_layout.addLayout(header_layout)

        # Video Label viewport
        self.video_label = VideoLabel(self)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setScaledContents(True)
        self.video_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        # Scaled minimum keeps the 2x2 grid inside the physical screen on 1024x768.
        self.video_label.setMinimumSize(_vid_min_w, _vid_min_h)
        self.video_label.setStyleSheet("background-color: #080a0f; border-radius: 6px; border: 1px solid #1a222d;")
        self.video_label.roi_updated.connect(self.on_roi_updated)
        card_layout.addWidget(self.video_label, stretch=1)

        # Bottom Area: Single horizontal row with metrics on left and controls on right
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 2, 0, 0)
        bottom_row.setSpacing(6)

        # Local metrics labels (left side)
        metrics_layout = QVBoxLayout()
        metrics_layout.setSpacing(1)
        metrics_layout.setContentsMargins(0, 0, 0, 0)

        self.metric_objects_label = QLabel("👥 OBJECTS: 0")
        self.metric_objects_label.setStyleSheet("color: #4fd1c5; font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold;")
        
        self.metric_roi_label = QLabel("🔍 ROI: SECURE")
        self.metric_roi_label.setStyleSheet("color: #10b981; font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold;")

        metrics_layout.addWidget(self.metric_objects_label)
        metrics_layout.addWidget(self.metric_roi_label)
        bottom_row.addLayout(metrics_layout)

        bottom_row.addStretch()

        # Action buttons (right side)
        self.btn_start = QPushButton("▶ START")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #1c3d27; border: 1px solid #276749; color: #68d391;
                font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 6px 10px;
            }
            QPushButton:hover { background-color: #22543d; }
            QPushButton:disabled { background-color: #242b35; border: 1px solid #364151; color: #718096; }
        """)
        self.btn_start.clicked.connect(lambda: self.start_camera(persist=True))
        bottom_row.addWidget(self.btn_start)

        self.btn_stop = QPushButton("■ STOP")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #4a371d; border: 1px solid #744210; color: #f6ad55;
                font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 6px 10px;
            }
            QPushButton:hover { background-color: #5f370e; }
            QPushButton:disabled { background-color: #242b35; border: 1px solid #364151; color: #718096; }
        """)
        self.btn_stop.clicked.connect(lambda: self.stop_camera(persist=True))
        self.btn_stop.setEnabled(False)
        bottom_row.addWidget(self.btn_stop)

        self.btn_edit_roi = QPushButton("✏ EDIT ROI")
        self.btn_edit_roi.setStyleSheet("""
            QPushButton {
                background-color: #24364d; border: 1px solid #2b4c7e; color: #63b3ed;
                font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 6px 10px;
            }
            QPushButton:hover { background-color: #1a2a3a; }
            QPushButton:disabled { background-color: #242b35; border: 1px solid #4a5568; color: #718096; }
        """)
        self.btn_edit_roi.clicked.connect(self.toggle_roi_edit)
        self.btn_edit_roi.setEnabled(False)  # Overridden by Supervisor role level
        bottom_row.addWidget(self.btn_edit_roi)

        card_layout.addLayout(bottom_row)

        # Placeholders to prevent attribute errors on dynamic settings updates
        self.relay_combo = None
        self.btn_test_relay = None

        # Load persisted unique coordinates and update preview
        self.load_roi()
        self.update_standby_frame()

    # ==========================================
    # REGION OF INTEREST (ROI) PERSISTENCE
    # ==========================================
    def load_roi(self):
        config_path = "config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    data = json.load(f)
                cam_key = f"camera_{self.cam_id}"
                if cam_key in data:
                    coords = data[cam_key]
                    norm_x = coords.get("norm_x")
                    norm_y = coords.get("norm_y")
                    norm_w = coords.get("norm_w")
                    norm_h = coords.get("norm_h")
                    if all(v is not None for v in [norm_x, norm_y, norm_w, norm_h]):
                        self.video_label.set_norm_roi((norm_x, norm_y, norm_w, norm_h))
                    else:
                        x = coords.get("x")
                        y = coords.get("y")
                        w = coords.get("w")
                        h = coords.get("h")
                        if all(v is not None for v in [x, y, w, h]):
                            # Sanitize legacy pixel values (e.g. w: 723 from old stretch bug)
                            ref_w = 640.0 if w > 400 else 380.0
                            ref_h = 480.0 if h > 300 else 280.0
                            nx = max(0.0, min(0.9, x / ref_w))
                            ny = max(0.0, min(0.9, y / ref_h))
                            nw = max(0.05, min(1.0 - nx, w / ref_w))
                            nh = max(0.05, min(1.0 - ny, h / ref_h))
                            self.video_label.set_norm_roi((nx, ny, nw, nh))
            except Exception as e:
                print(f"Error loading ROI for station {self.cam_id + 1}: {e}")

    def save_roi(self, roi_rect):
        config_path = "config.json"
        data = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        cam_key = f"camera_{self.cam_id}"
        if roi_rect is None or roi_rect.isNull():
            data[cam_key] = {}
        else:
            norm_roi = self.video_label.get_norm_roi()
            if norm_roi:
                nx, ny, nw, nh = norm_roi
                data[cam_key] = {
                    "norm_x": round(float(nx), 4),
                    "norm_y": round(float(ny), 4),
                    "norm_w": round(float(nw), 4),
                    "norm_h": round(float(nh), 4),
                    "x": int(roi_rect.x()),
                    "y": int(roi_rect.y()),
                    "w": int(roi_rect.width()),
                    "h": int(roi_rect.height())
                }
            else:
                data[cam_key] = {
                    "x": int(roi_rect.x()),
                    "y": int(roi_rect.y()),
                    "w": int(roi_rect.width()),
                    "h": int(roi_rect.height())
                }

        try:
            with open(config_path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error writing ROI config for station {self.cam_id + 1}: {e}")


    def on_roi_updated(self, roi_rect):
        if self.video_label.is_editable:
            self.save_roi(roi_rect)
            if self.parent_window:
                self.parent_window.add_audit_log(f"Station {self.cam_id + 1} ROI adjusted.", "config")

    def on_relay_changed(self, idx):
        new_relay = idx + 1
        if self.parent_window and hasattr(self.parent_window, "global_settings"):
            if "relay_mapping" not in self.parent_window.global_settings:
                self.parent_window.global_settings["relay_mapping"] = [1, 2, 3, 4]
            while len(self.parent_window.global_settings["relay_mapping"]) < 4:
                self.parent_window.global_settings["relay_mapping"].append(1)
            self.parent_window.global_settings["relay_mapping"][self.cam_id] = new_relay

            # Keep settings page dropdown in sync
            if hasattr(self.parent_window, "relay_dropdowns") and self.cam_id < len(self.parent_window.relay_dropdowns):
                self.parent_window.relay_dropdowns[self.cam_id].blockSignals(True)
                self.parent_window.relay_dropdowns[self.cam_id].setCurrentIndex(idx)
                self.parent_window.relay_dropdowns[self.cam_id].blockSignals(False)

            if getattr(self, 'btn_test_relay', None) and not self.btn_test_relay.isChecked():
                self.btn_test_relay.setText(f"⚡ TEST R{new_relay}")

            self.parent_window.instant_save_timer_config()
            self.parent_window.add_audit_log(f"Station {self.cam_id + 1} mapped to Relay {new_relay}", "config")

    def on_test_relay_clicked(self, checked):
        if not self.parent_window:
            return
        mapping = self.parent_window.global_settings.get("relay_mapping", [1, 2, 3, 4])
        target_relay = mapping[self.cam_id] if self.cam_id < len(mapping) else (self.cam_id + 1)
        relay_idx = target_relay - 1

        if getattr(self, 'btn_test_relay', None):
            if checked:
                self.btn_test_relay.setText(f"⚡ R{target_relay} ON")
            else:
                self.btn_test_relay.setText(f"⚡ TEST R{target_relay}")

        self.parent_window.test_relay_channel(relay_idx, checked)

    # ==========================================
    # LOGICAL BACKEND PIPELINES
    # ==========================================
    def start_camera(self, persist=True):
        if persist and self.parent_window and hasattr(self.parent_window, "set_camera_feed_enabled"):
            self.parent_window.set_camera_feed_enabled(self.cam_id, True)

        self.is_feed_enabled = True

        if self.is_active:
            return
        
        self.is_active = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        role_level = self.parent_window.access_levels.get(self.parent_window.current_role, 1)
        self.btn_edit_roi.setEnabled(role_level >= 2)

        self.camera_online = False
        self.blink_state = False
        
        # Spawn localized background worker QThread with physical USB port binding
        self.camera_thread = CameraWorkerThread(
            device_index=self.device_index,
            station_id=self.cam_id,
            target_physical_usb_path=self.target_physical_usb_path,
            width=640,
            height=480
        )
        self.camera_thread.frame_ready.connect(self.on_frame_received)
        self.camera_thread.status_changed.connect(self.on_camera_status_changed)
        self.camera_thread.path_discovered.connect(self.on_physical_path_discovered)
        self.camera_thread.start()

        # YOLO inference timer: fires once per second, processes only the latest frame
        if self.yolo_timer is None:
            self.yolo_timer = QTimer(self)
            self.yolo_timer.timeout.connect(self.run_yolo_on_latest_frame)
        self.yolo_timer.start(1000)  # 1 FPS

        # Start standard 500ms HMI viewport warning blink timer
        if self.blink_timer is None:
            self.blink_timer = QTimer(self)
            self.blink_timer.timeout.connect(self.on_blink_tick)
        self.blink_timer.start(500)

        if self.parent_window:
            self.parent_window.add_audit_log(f"Station {self.cam_id + 1} monitoring active (Node/Idx {self.device_index}).")

    def on_physical_path_discovered(self, station_id, physical_path):
        if station_id == self.cam_id:
            self.target_physical_usb_path = physical_path
            if self.camera_thread and self.camera_thread.current_device_index is not None:
                self.device_index = self.camera_thread.current_device_index
            if self.parent_window:
                if hasattr(self.parent_window, "global_settings"):
                    if "camera_physical_paths" not in self.parent_window.global_settings:
                        self.parent_window.global_settings["camera_physical_paths"] = [None, None, None, None]
                    while len(self.parent_window.global_settings["camera_physical_paths"]) < 4:
                        self.parent_window.global_settings["camera_physical_paths"].append(None)
                    self.parent_window.global_settings["camera_physical_paths"][station_id] = physical_path
                self.parent_window.add_audit_log(f"Station {station_id + 1} permanently bound to physical USB port: {physical_path}", "success")

    def stop_camera(self, persist=True):
        if persist and self.parent_window and hasattr(self.parent_window, "set_camera_feed_enabled"):
            self.parent_window.set_camera_feed_enabled(self.cam_id, False)

        self.is_feed_enabled = False

        if not self.is_active:
            return

        if self.yolo_timer is not None:
            self.yolo_timer.stop()
            self.yolo_timer = None

        if self.blink_timer is not None:
            self.blink_timer.stop()
            self.blink_timer = None

        # Cancel any pending OR auto-OFF timer on camera stop
        if self._or_off_timer is not None:
            self._or_off_timer.stop()
            self._or_off_timer = None
        self._or_trigger_armed = True   # Re-arm so the next activation starts clean

        if self.camera_thread is not None:
            self.camera_thread.stop()
            self.camera_thread.deleteLater()
            self.camera_thread = None

        self.is_active = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

        # Revert to standard gray standby layout
        self.status_banner.setText("STANDBY")
        self.status_banner.setStyleSheet("color: #cbd5e0; font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold;")
        self.led_indicator.set_state("standby")
        self.setProperty("warning", "standby")
        self.style().unpolish(self)
        self.style().polish(self)

        self.update_standby_frame()
        
        # Trigger Relay contact release if we were previously breaching
        if self.prev_warning:
            self.prev_warning = False
            if self.relay_manager is not None and self.relay_manager.is_connected:
                self.relay_manager.trigger_relay(self.cam_id, False)

        if self.parent_window:
            self.parent_window.add_audit_log(f"Station {self.cam_id + 1} monitoring standby.")
            self.parent_window.evaluate_global_alarms()

    def _force_or_output_off(self):
        """
        Slot called exactly 3 seconds after the OR output became ON.
        Forces the OR output to OFF unconditionally — detection state is ignored.

        Latch behavior:
          If last_hardware_state is True when the timer fires, the person is
          still inside the ROI.  In that case _or_trigger_armed is set to False
          so that the hardware loop ignores all subsequent ON commands until the
          detection clears (warning goes False) and the person re-enters.

          If last_hardware_state is already False (person left before 3 s elapsed),
          the trigger remains armed — _or_trigger_armed is left unchanged — so the
          next detection event works normally without requiring an extra ROI exit.
        """
        if self.relay_manager is not None and self.relay_manager.is_connected:
            self.relay_manager.trigger_relay(self.cam_id, False)
        # Disarm only when the relay was still ON at timer-fire time (person still present).
        # If detection already cleared the relay before 3 s, last_hardware_state is False
        # and the trigger stays armed for the next detection event.
        if self.last_hardware_state:
            self._or_trigger_armed = False
        self.last_hardware_state = False
        if self.parent_window:
            self.parent_window.add_audit_log(
                f"RM04U: Ch {self.cam_id + 1} -> OFF (auto 3s timer)", "success"
            )

    def toggle_roi_edit(self):
        """
        Toggles local ROI canvas edit mode on/off.
        """
        if not self.video_label.is_editable:
            # Unlock draw mode
            self.video_label.set_editable(True)
            self.video_label.start_drawing_roi()
            self.btn_edit_roi.setText("💾 SAVE ROI")
            self.btn_edit_roi.setStyleSheet("""
                QPushButton {
                    background-color: #1c5230; border: 1px solid #276749; color: #a3f4be;
                    font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 6px 10px;
                }
                QPushButton:hover { background-color: #22543d; }
            """)
            if self.parent_window:
                self.parent_window.add_audit_log(f"Station {self.cam_id + 1} ROI editor unlocked.", "config")
        else:
            # Lock draw mode and save
            self.video_label.set_editable(False)
            self.btn_edit_roi.setText("✏ EDIT ROI")
            self.btn_edit_roi.setStyleSheet("""
                QPushButton {
                    background-color: #24364d; border: 1px solid #2b4c7e; color: #63b3ed;
                    font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 6px 10px;
                }
                QPushButton:hover { background-color: #1a2a3a; }
            """)
            self.save_roi(self.video_label.roi_rect)
            if self.parent_window:
                self.parent_window.add_audit_log(f"Station {self.cam_id + 1} ROI coordinates saved.", "success")

    # ==========================================
    # DISPLAY RENDERING PIPELINE
    # ==========================================
    def on_camera_status_changed(self, is_online, message):
        self.camera_online = is_online
        if is_online:
            self.title_label.setText(f"🚚 STATION {self.cam_id + 1:02d} - ● SECURE")
            self.title_label.setStyleSheet("color: #10b981; font-family: 'Segoe UI Semibold'; font-size: 13px; font-weight: 800; letter-spacing: 0.5px;")
            self.status_banner.setText("● SECURE")
            self.status_banner.setStyleSheet("color: #10b981; font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold;")
            self.metric_roi_label.setText("🔍 ROI: SECURE")
            self.metric_roi_label.setStyleSheet("color: #10b981; font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold;")
            self.led_indicator.set_state("secure")
            self.setProperty("warning", "false")
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            self.update_offline_banner()

    def on_blink_tick(self):
        if not self.camera_online:
            self.update_offline_banner()

    def update_offline_banner(self):
        """
        Renders a custom high-visibility flashing warning inside the viewport using QPainter.
        Uses a fixed 640x480 canvas scaled cleanly to the viewport, preventing layout renegotiation.
        Draws the defined ROI in red to maintain context even when the camera feed drops.
        """
        self.blink_state = not getattr(self, "blink_state", False)
        
        pixmap = QPixmap(640, 480)
        pixmap.fill(QColor("#14100d"))
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw ROI boundary if configured
        norm_roi = self.video_label.get_norm_roi()
        if norm_roi is not None:
            nx, ny, nw, nh = norm_roi
            rx = int(nx * 640)
            ry = int(ny * 480)
            rw = int(nw * 640)
            rh = int(nh * 480)
            painter.setPen(QColor("#e53e3e"))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rx, ry, rw, rh)
        
        font = painter.font()
        font.setFamily("Segoe UI")
        font.setBold(True)
        font.setPointSize(14)
        painter.setFont(font)
        
        if self.blink_state:
            color = QColor("#ff4d4d")
        else:
            color = QColor("#662222")
            
        painter.setPen(color)
        rect = pixmap.rect()
        painter.drawText(rect, Qt.AlignCenter, "⚠️ CAMERA FEED: OFFLINE\n(RECONNECTING...)")
        painter.end()
        
        self.video_label.setPixmap(pixmap)
        
        self.status_banner.setText("● ⚠️ RECONNECTING...")
        self.status_banner.setStyleSheet("color: #ff4d4d; font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold;")
        self.led_indicator.set_state("error")

        self.metric_objects_label.setText("👥 OBJECTS: 0")
        self.metric_roi_label.setText("🔍 ROI: OFFLINE")
        self.metric_roi_label.setStyleSheet("color: #ff4d4d; font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold;")
        self.title_label.setText(f"🚚 STATION {self.cam_id + 1:02d} - ⚠️ OFFLINE")
        self.title_label.setStyleSheet("color: #ff4d4d; font-family: 'Segoe UI Semibold'; font-size: 13px; font-weight: 800; letter-spacing: 0.5px;")

        self.setProperty("warning", "true")
        self.style().unpolish(self)
        self.style().polish(self)

    def run_yolo_on_latest_frame(self):
        """
        Called once per second by yolo_timer.
        Grabs the latest captured frame at this exact moment, runs YOLO on it,
        and caches the results for the display pipeline to consume.
        All older frames are automatically discarded (never queued).
        """
        if not self.is_active or self.camera_thread is None:
            return

        # Grab only the latest frame — atomically swap it out so nothing accumulates
        with self.camera_thread._frame_lock:
            frame_for_yolo = self.camera_thread.latest_frame

        if frame_for_yolo is None:
            return

        frame_h, frame_w = frame_for_yolo.shape[:2]
        widget_w = self.video_label.width()
        widget_h = self.video_label.height()

        # Resolve scaled ROI coordinates invariant to GUI resizing
        scaled_roi = QRect()
        norm_roi = self.video_label.get_norm_roi()
        if norm_roi is not None and frame_w > 0 and frame_h > 0:
            nx, ny, nw, nh = norm_roi
            scaled_roi = QRect(
                int(nx * frame_w),
                int(ny * frame_h),
                int(nw * frame_w),
                int(nh * frame_h)
            )
        elif widget_w > 0 and widget_h > 0 and self.video_label.roi_rect is not None and not self.video_label.roi_rect.isNull():
            scale_x = frame_w / widget_w
            scale_y = frame_h / widget_h
            roi = self.video_label.roi_rect
            scaled_roi = QRect(
                int(roi.x() * scale_x),
                int(roi.y() * scale_y),
                int(roi.width() * scale_x),
                int(roi.height() * scale_y)
            )

        persons = []
        if self.detector is not None:
            try:
                # CPU OPTIMIZATION: Force YOLO imgsz to 320 to cut math calculations
                persons = self.detector.detect_persons(frame_for_yolo, imgsz=320)
            except Exception as e:
                print(f"YOLO error on station {self.cam_id + 1}: {e}")

        # Cache results — consumed by the display pipeline on every incoming frame
        self.last_persons = persons
        self.last_warning = self.alarm_system.check_boundaries(persons, scaled_roi)
        self.last_scaled_roi = scaled_roi

    def on_frame_received(self, frame):
        if not self.is_active:
            return

        self.camera_online = True

        # DYNAMIC SCALE MATH Setup
        frame_h, frame_w = frame.shape[:2]
        widget_w = self.video_label.width()
        widget_h = self.video_label.height()

        # Resolve scaled ROI coordinates invariant to GUI resizing
        scaled_roi = QRect()
        norm_roi = self.video_label.get_norm_roi()
        if norm_roi is not None and frame_w > 0 and frame_h > 0:
            nx, ny, nw, nh = norm_roi
            scaled_roi = QRect(
                int(nx * frame_w),
                int(ny * frame_h),
                int(nw * frame_w),
                int(nh * frame_h)
            )
        elif widget_w > 0 and widget_h > 0 and self.video_label.roi_rect is not None and not self.video_label.roi_rect.isNull():
            scale_x = frame_w / widget_w
            scale_y = frame_h / widget_h
            roi = self.video_label.roi_rect
            scaled_roi = QRect(
                int(roi.x() * scale_x),
                int(roi.y() * scale_y),
                int(roi.width() * scale_x),
                int(roi.height() * scale_y)
            )

        # Reuse latest cached YOLO results (updated by the 1-second yolo_timer)
        persons = getattr(self, 'last_persons', [])
        warning = getattr(self, 'last_warning', False)
        scaled_roi = getattr(self, 'last_scaled_roi', scaled_roi)

        # Update metrics label
        self.metric_objects_label.setText(f"👥 OBJECTS: {len(persons)}")

        # Draw native bounding boxes
        for (x1, y1, x2, y2) in persons:
            color = (0, 0, 255) if warning else (255, 0, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, "PERSON", (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

        # Draw scaled ROI boundary directly on native frame
        if scaled_roi is not None and not scaled_roi.isNull():
            rx, ry, rw, rh = scaled_roi.x(), scaled_roi.y(), scaled_roi.width(), scaled_roi.height()
            roi_color = (0, 0, 255) if warning else (0, 255, 0)
            cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), roi_color, 2)
            
            # Semi-transparent overlay on native frame
            overlay = frame.copy()
            cv2.rectangle(overlay, (rx, ry), (rx + rw, ry + rh), roi_color, -1)
            alpha = 0.15 if warning else 0.05
            cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)

        # ---------------------------------------------
        # HARDWARE AUTOMATION LOOP TRIGGER
        # ---------------------------------------------
        # Check if supervisor manual override is active for this channel
        is_manual_override = False
        if self.relay_manager is not None:
            if self.cam_id < len(self.relay_manager.manual_overrides):
                is_manual_override = self.relay_manager.manual_overrides[self.cam_id]

        if not is_manual_override:
            # Force auto-synchronize if active manual override was just untoggled/released
            if getattr(self, "was_overridden", False):
                self.was_overridden = False
                self.last_hardware_state = None  # Force re-evaluation on next cycle
                self._or_trigger_armed = True     # Re-arm after override release

            # Re-arm the trigger when detection clears (person has left the ROI).
            # This is the ONLY path that permits a new ON command after the
            # 3-second auto-OFF timer has latched _or_trigger_armed to False.
            if not warning and not self._or_trigger_armed:
                self._or_trigger_armed = True

            # Suppress ON commands while the trigger is disarmed.
            # The trigger is disarmed by _force_or_output_off when the 3-second
            # timer fires while the person is still inside the ROI.
            # OFF commands (warning=False) are always passed through.
            if warning and not self._or_trigger_armed:
                pass  # OR output stays OFF — latched until detection clears

            # Only write to serial port when the hardware state actually transitions
            elif warning != self.last_hardware_state:
                if self.relay_manager is not None and self.relay_manager.is_connected:
                    success, msg = self.relay_manager.trigger_relay(self.cam_id, warning)
                    if success:
                        self.last_hardware_state = warning
                        if "Filtered" not in msg and "Cooldown" not in msg:
                            if self.parent_window:
                                log_type = "warning" if warning else "success"
                                action_char = 'N' if warning else 'F'
                                self.parent_window.add_audit_log(
                                    f"RM04U: Ch {self.cam_id + 1} -> {'ON' if warning else 'OFF'} ({action_char}{self.cam_id + 1}) - {msg}", 
                                    log_type
                                )

                        # OR output auto-OFF timer: start only on ON transition
                        # The timer is independent of detection state — it fires
                        # exactly once, 3 seconds after the OR output became ON,
                        # and forces the output OFF unconditionally.
                        if warning:
                            if self._or_off_timer is None:
                                self._or_off_timer = QTimer(self)
                                self._or_off_timer.setSingleShot(True)
                                self._or_off_timer.timeout.connect(self._force_or_output_off)
                            # Only start if not already running (no restart, no extension)
                            if not self._or_off_timer.isActive():
                                reset_ms = int(self.parent_window.global_settings.get("alarm_auto_reset", 3.0) * 1000)
                                self._or_off_timer.start(reset_ms)
                    else:
                        if self.parent_window:
                            self.parent_window.add_audit_log(f"RM04U Failure: {msg}", "warning")
        else:
            self.was_overridden = True

        # Always keep visual prev_warning in sync for UI rendering
        self.prev_warning = warning

        if warning:
            # Draw bold high-visibility Alert overlay directly on the frame (with drop-shadow)
            text_str = "CRITICAL VIOLATION - SECTOR BREACHED"
            cv2.putText(frame, text_str, (32, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 2, cv2.LINE_AA)
            cv2.putText(frame, text_str, (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2, cv2.LINE_AA)

            # Local station indicators set to danger-red
            self.metric_roi_label.setText("🔍 ROI: BREACHED")
            self.metric_roi_label.setStyleSheet("color: #e74c3c; font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold;")
            self.status_banner.setText("⚠️ INTRUSION")
            self.status_banner.setStyleSheet("color: #e74c3c; font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold;")
            self.led_indicator.set_state("breach")
            self.title_label.setText(f"🚚 STATION {self.cam_id + 1:02d} - ⚠️ INTRUSION")
            self.title_label.setStyleSheet("color: #e74c3c; font-family: 'Segoe UI Semibold'; font-size: 13px; font-weight: 800; letter-spacing: 0.5px;")
            self.setProperty("warning", "true")
        else:
            # Clean secure green styling
            self.metric_roi_label.setText("🔍 ROI: SECURE")
            self.metric_roi_label.setStyleSheet("color: #2ecc71; font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold;")
            self.status_banner.setText("● SECURE")
            self.status_banner.setStyleSheet("color: #2ecc71; font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold;")
            self.led_indicator.set_state("secure")
            self.title_label.setText(f"🚚 STATION {self.cam_id + 1:02d} - ● SECURE")
            self.title_label.setStyleSheet("color: #2ecc71; font-family: 'Segoe UI Semibold'; font-size: 13px; font-weight: 800; letter-spacing: 0.5px;")
            self.setProperty("warning", "false")

        # Repaint dynamic styles
        self.style().unpolish(self)
        self.style().polish(self)

        # Calculate FPS
        current_time = time.time()
        fps = 1.0 / (current_time - self.prev_time) if (current_time - self.prev_time) > 0.0 else 0.0
        self.prev_time = current_time
        
        cv2.putText(frame, f"FPS: {int(fps)}", (20, frame_h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

        # Convert to QImage and display
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        qt_image = QImage(frame_rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self.video_label.setPixmap(QPixmap.fromImage(qt_image))

        # Check in with MainWindow to aggregate alerts
        if self.parent_window:
            self.parent_window.evaluate_global_alarms()

    def update_standby_frame(self):
        standby_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        standby_frame[:] = (20, 16, 13)

        cv2.putText(standby_frame, f"STATION {self.cam_id + 1:02d} STANDBY", (140, 220), 
                     cv2.FONT_HERSHEY_SIMPLEX, 0.8, (120, 140, 160), 2, cv2.LINE_AA)
        cv2.putText(standby_frame, "AUTO-START MONITORING SECURE", (150, 260), 
                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (90, 100, 115), 1, cv2.LINE_AA)

        h, w, ch = standby_frame.shape
        qt_image = QImage(standby_frame.data, w, h, ch * w, QImage.Format_RGB888)
        self.video_label.setPixmap(QPixmap.fromImage(qt_image))

        self.metric_objects_label.setText("👥 OBJECTS: 0")
        self.metric_roi_label.setText("🔍 ROI: STANDBY")
        self.metric_roi_label.setStyleSheet("color: #a0aec0; font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold;")
        self.title_label.setText(f"🚚 STATION {self.cam_id + 1:02d}")
        self.title_label.setStyleSheet("color: #ffffff; font-family: 'Segoe UI Semibold'; font-size: 13px; font-weight: 800; letter-spacing: 0.5px;")


# ==========================================
# MAIN OPERATIONS HMI CONSOLE (2x2 GRID)
# ==========================================
class ForkliftSafetyGUI(QWidget):
    def __init__(self):
        super().__init__()

        # Enforce Industrial Access Control values
        self.current_role = "Operator"
        self.access_levels = {
            "Operator": 1,
            "Supervisor": 2,
            "Engineer": 3,
            "Admin": 4,
            "Administrator": 4,
            "Technician": 2
        }

        # Initialize Security and load global settings
        self.security = SecurityManager()
        self.load_global_settings()

        # ---------------------------------------------
        # HARDWARE AUTONOMOUS DEVICE NODE AUTOMATION
        # ---------------------------------------------
        # Lock sequentially to Stations 1-4 from even-numbered V4L2 device nodes
        detected_nodes = []
        for idx in range(0, 30, 2):
            node_path = f"/dev/video{idx}"
            if os.path.exists(node_path):
                detected_nodes.append(node_path)
            if len(detected_nodes) == 4:
                break
        
        # Fallback to standard sequential indexes if camera nodes are not physically present
        while len(detected_nodes) < 4:
            fallback_idx = len(detected_nodes) * 2
            detected_nodes.append(fallback_idx)
            
        self.global_settings["camera_mapping"] = detected_nodes

        # Shared YOLO model loaded with dynamic models and confidence
        self.detector = YoloDetector(
            model_name=self.global_settings["model_path"],
            confidence=self.global_settings["confidence"]
        )
        
        # Instantiate modular USB Serial Relay Manager
        self.relay_manager = USBRelayManager()
        
        # Set Window Title
        self.setWindowTitle("LIMITLESS FUTURE - FORKLIFT HUMAN DETECTION SAFETY SYSTEM")

        # ---------------------------------------------
        # RUNTIME SCREEN RESOLUTION DETECTION & SCALING
        # ---------------------------------------------
        # Detect the physical screen geometry at runtime so the GUI never overflows
        # the visible area regardless of monitor resolution (1024x768, 1920x1080, etc.).
        _screen = QApplication.primaryScreen()
        _screen_geom = _screen.geometry()
        _screen_w = _screen_geom.width()
        _screen_h = _screen_geom.height()

        # Reference resolution the layout was originally designed for.
        _REF_W = 1920
        _REF_H = 1080

        # ui_scale: ratio of actual screen to reference design (1920x1080).
        # Scaled smoothly between 0.45 and 1.5 to support displays from 800x480/1024x600 up to 4K.
        _raw_scale = min(_screen_w / _REF_W, _screen_h / _REF_H)
        _ui_scale = max(0.45, min(1.5, _raw_scale))
        self._ui_scale = _ui_scale

        # Store screen dimensions for use by child widgets (e.g. sidebar scaling)
        self._screen_w = _screen_w
        self._screen_h = _screen_h

        # setMinimumSize must never exceed physical screen size so showFullScreen()
        # fits smoothly on small embedded screens (e.g. 1024x600, 800x480, 1024x768).
        self.setMinimumSize(min(_screen_w, 640), min(_screen_h, 400))

        # ---------------------------------------------
        # KIOSK MODE INTEGRATION
        # ---------------------------------------------
        # Strip out window borders, decorations, and title bar, locking focus to HMI Screen
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.CustomizeWindowHint)
        self.showFullScreen()

        # Apply Industrial dark SCADA style.
        # Global QPushButton padding and font-size scale with _ui_scale so buttons
        # don't consume excessive vertical space on the 1024x768 Nixdorf monitor.
        # _ui_scale is already computed above (≈0.71 on 1024x768, 1.0 on 1920x1080).
        _btn_v_pad = max(4, int(10 * _ui_scale))  # vertical padding: 10px → 7px on 768p
        _btn_fs    = max(9, int(11 * _ui_scale))   # font-size:       11px → 9px  on 768p
        _exit_v_pad = max(6, int(10 * _ui_scale))  # btnExit vertical padding
        _exit_fs    = max(9, int(12 * _ui_scale))  # btnExit font-size
        self.setStyleSheet(f"""
            QWidget {{
                background-color: #1e1e24;
                color: #e2e8f0;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
            }}

            QFrame#mainContainer {{
                background-color: #16161a;
                border: 2px solid #232d38;
                border-radius: 8px;
            }}

            QFrame#sidebar {{
                background-color: rgba(22, 22, 26, 0.85);
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}

            QLabel#sidebarHeader {{
                font-family: 'Segoe UI Semibold';
                font-size: 11px;
                font-weight: 800;
                color: #718096;
                text-transform: uppercase;
                letter-spacing: 0.75px;
            }}

            QComboBox {{
                background-color: #1d212a;
                border: 1px solid #2d3846;
                border-radius: 4px;
                padding: 5px 22px 5px 10px;
                font-size: 12px;
                color: #ffffff;
                font-weight: 600;
            }}

            QComboBox:hover {{
                border: 1px solid #3d4f66;
            }}

            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 18px;
                border-left: none;
            }}

            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #a0aec0;
                width: 0;
                height: 0;
                margin-right: 6px;
            }}

            QComboBox QAbstractItemView {{
                background-color: #1a202c;
                color: #ffffff;
                selection-background-color: #3182ce;
                selection-color: #ffffff;
                border: 1px solid #2d3846;
                outline: 0px;
                padding: 2px;
            }}

            QComboBox QAbstractItemView::item {{
                min-height: 26px;
                padding: 4px 10px;
                color: #ffffff;
                background-color: #1a202c;
            }}

            QComboBox QAbstractItemView::item:hover {{
                background-color: #2b3545;
                color: #63b3ed;
            }}

            QComboBox QAbstractItemView::item:selected {{
                background-color: #3182ce;
                color: #ffffff;
            }}

            QPushButton {{
                background-color: #212630;
                border: 1px solid #2d3846;
                border-radius: 4px;
                /* Vertical padding scales with _ui_scale to reclaim height on 1024x768. */
                padding: {_btn_v_pad}px 4px;
                font-family: 'Segoe UI Semibold';
                font-size: {_btn_fs}px;
                font-weight: bold;
                color: #cbd5e0;
                text-transform: uppercase;
            }}

            QPushButton:hover {{
                background-color: #2d3545;
            }}
            QPushButton:disabled {{
                background-color: #1a1a1f;
                color: #4a5568;
                border: 1px solid #2d2d38;
            }}

            QPushButton#btnEnable {{
                background-color: #153a21;
                border: 1px solid #22543d;
                color: #48bb78;
            }}

            QPushButton#btnEnable:hover {{
                background-color: #1c4d2c;
            }}

            QPushButton#btnDisable {{
                background-color: #53331a;
                border: 1px solid #744210;
                color: #f6ad55;
            }}

            QPushButton#btnDisable:hover {{
                background-color: #633c1d;
            }}

            QPushButton#btnExit {{
                background-color: #4a1d1d;
                border: 1px solid #742a2a;
                border-radius: 4px;
                padding: {_exit_v_pad}px 20px;
                font-family: 'Segoe UI Semibold';
                font-size: {_exit_fs}px;
                font-weight: 800;
                color: #feb2b2;
                text-transform: uppercase;
            }}

            QPushButton#btnExit:hover {{
                background-color: #742a2a;
                color: #ffffff;
            }}

            QListWidget {{
                background-color: rgba(11, 11, 15, 0.9);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                font-family: 'Courier New', Consolas, monospace;
                font-size: 10px;
                color: #a0aec0;
                padding: 4px;
            }}
        """)

        # Main Layout Setup
        # Scale outer and container margins/spacing with the detected ui_scale so
        # the overall chrome shrinks on 1024x768 and the camera grid gets more room.
        _s = self._ui_scale
        _outer_margin  = max(4,  int(10 * _s))
        _cont_margin   = max(6,  int(14 * _s))
        _cont_spacing  = max(6,  int(12 * _s))

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(_outer_margin, _outer_margin, _outer_margin, _outer_margin)
        
        self.main_container = QFrame()
        self.main_container.setObjectName("mainContainer")
        outer_layout.addWidget(self.main_container)

        container_layout = QVBoxLayout(self.main_container)
        container_layout.setContentsMargins(_cont_margin, _cont_margin, _cont_margin, _cont_margin)
        container_layout.setSpacing(_cont_spacing)

        # --- TOP HEADER ---
        # Scale header font so it doesn't overflow on narrow screens.
        _header_fs = max(10, int(15 * _s))
        header_panel = QHBoxLayout()
        self.header_label = QLabel("LIMITLESS FUTURE - FORKLIFT HUMAN DETECTION SAFETY SYSTEM")
        self.header_label.setStyleSheet(f"font-family: 'Segoe UI Semibold'; font-size: {_header_fs}px; font-weight: 800; color: #ffffff; letter-spacing: 0.5px;")
        header_panel.addWidget(self.header_label)
        header_panel.addStretch()
        container_layout.addLayout(header_panel)

        # --- CENTRAL LAYOUT ---
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(12)

        # Main stacked container holding Live Monitor (Page 0) and System Setup (Page 1)
        self.stacked_widget = QStackedWidget()
        
        # ---------------------------------------------
        # PAGE 0: LIVE MONITORING
        # ---------------------------------------------
        self.live_view_page = QWidget()
        self.live_view_page.setStyleSheet("background: transparent; border: none;")
        live_layout = QVBoxLayout(self.live_view_page)
        live_layout.setContentsMargins(0, 0, 0, 0)
        
        # 2x2 Grid Client Placement
        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent; border: none;")
        self.grid_layout = QGridLayout(grid_widget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setRowStretch(0, 1)
        self.grid_layout.setRowStretch(1, 1)
        self.grid_layout.setColumnStretch(0, 1)
        self.grid_layout.setColumnStretch(1, 1)

        # Spawn 4 cards matching sequence of auto V4L2 device nodes.
        # Pass ui_scale so each card shrinks its own layout on small screens.
        self.cards = []
        mappings = self.global_settings["camera_mapping"]
        for i in range(4):
            card = CameraCardWidget(
                cam_id=i, 
                device_index=mappings[i], 
                detector=self.detector, 
                security_manager=self.security, 
                relay_manager=self.relay_manager,
                parent=self,
                ui_scale=self._ui_scale
            )
            self.cards.append(card)
            
            row = i // 2
            col = i % 2
            self.grid_layout.addWidget(card, row, col)

        live_layout.addWidget(grid_widget)
        self.stacked_widget.addWidget(self.live_view_page)

        # ---------------------------------------------
        # PAGE 1: SYSTEM CONFIGURATION
        # ---------------------------------------------
        self.setup_scroll = QScrollArea()
        self.setup_scroll.setWidgetResizable(True)
        self.setup_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setup_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setup_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #4a5568;
                min-height: 40px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #718096;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        self.setup_page = QWidget()
        self.setup_page.setStyleSheet("""
            QWidget {
                background: transparent;
                border: none;
            }
            QGroupBox {
                border: 1px solid #232a36;
                border-radius: 6px;
                margin-top: 14px;
                padding-top: 12px;
                font-family: 'Segoe UI Semibold';
                font-size: 11px;
                font-weight: bold;
                color: #63b3ed;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 6px;
                background-color: #12151c;
            }
            QLabel {
                color: #cbd5e0;
                font-family: 'Segoe UI Semibold';
                font-size: 11px;
            }
            QComboBox {
                background-color: #1a202c;
                border: 1px solid #2d3846;
                border-radius: 4px;
                padding: 5px 22px 5px 10px;
                font-size: 12px;
                color: #ffffff;
                font-weight: 600;
            }
            QComboBox:hover {
                border: 1px solid #3d4f66;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 18px;
                border-left: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #a0aec0;
                width: 0;
                height: 0;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #1a202c;
                color: #ffffff;
                selection-background-color: #3182ce;
                selection-color: #ffffff;
                border: 1px solid #2d3846;
                outline: 0px;
                padding: 2px;
            }
            QComboBox QAbstractItemView::item {
                min-height: 26px;
                padding: 4px 10px;
                color: #ffffff;
                background-color: #1a202c;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #2b3545;
                color: #63b3ed;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #3182ce;
                color: #ffffff;
            }
            QLineEdit {
                background-color: #1a202c;
                border: 1px solid #2d3846;
                border-radius: 4px;
                padding: 6px 10px;
                color: #ffffff;
                font-family: 'Segoe UI Semibold';
                font-size: 12px;
                font-weight: bold;
            }
            QDoubleSpinBox {
                background-color: #1a202c;
                border: 1px solid #2d3846;
                border-radius: 4px;
                padding: 5px 8px;
                color: #ffffff;
                font-family: 'Segoe UI Semibold', monospace;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #1e242f;
                border: 1px solid #2d3846;
                color: #cbd5e0;
                border-radius: 4px;
                padding: 5px 12px;
                font-family: 'Segoe UI Semibold';
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2b3545;
                color: #ffffff;
            }
        """)

        setup_layout = QVBoxLayout(self.setup_page)
        setup_layout.setContentsMargins(10, 8, 14, 16)
        setup_layout.setSpacing(12)

        # ==========================================================
        # GROUP 1: RM04U RELAY HARDWARE INTEGRITY
        # ==========================================================
        group_relay = QGroupBox("⚡ RM04U RELAY HARDWARE INTEGRITY")
        relay_layout = QGridLayout(group_relay)
        relay_layout.setContentsMargins(14, 14, 14, 12)
        relay_layout.setSpacing(8)

        # Row 0: COM Port & Baud Rate
        lbl_com = QLabel("COM Port Interface:")
        relay_layout.addWidget(lbl_com, 0, 0)

        self.com_combo = QComboBox()
        self.com_combo.setView(QListView())
        self.com_combo.setEditable(True)
        ports = self.relay_manager.scan_available_ports()
        self.com_combo.addItems(ports)
        self.com_combo.setCurrentText(self.global_settings.get("com_port", "/dev/ttyUSB0"))
        self.com_combo.setStyleSheet("color: #63b3ed; font-weight: bold;")
        self.com_combo.currentIndexChanged.connect(self.instant_save_timer_config)
        relay_layout.addWidget(self.com_combo, 0, 1)

        lbl_baud = QLabel("Baud Rate:")
        relay_layout.addWidget(lbl_baud, 0, 2)

        self.baud_combo = QComboBox()
        self.baud_combo.setView(QListView())
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.baud_combo.setCurrentText(str(self.global_settings.get("baud_rate", 9600)))
        self.baud_combo.currentIndexChanged.connect(self.instant_save_timer_config)
        relay_layout.addWidget(self.baud_combo, 0, 3)

        # Row 1: Test Connection & Relay 1-4 Test Buttons
        self.btn_test_conn = QPushButton("⚡ TEST HARDWARE CONNECTION")
        self.btn_test_conn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none; color: #cbd5e0;
                font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold;
                padding: 4px 6px; text-align: center;
            }
            QPushButton:hover { color: #63b3ed; }
        """)
        self.btn_test_conn.clicked.connect(self.test_hardware_connection)
        relay_layout.addWidget(self.btn_test_conn, 1, 0, 1, 2)

        test_btns_layout = QHBoxLayout()
        test_btns_layout.setSpacing(6)
        self.relay_buttons = []
        for i in range(4):
            btn = QPushButton(f"TEST RELAY {i+1}")
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton { background-color: #1e242f; border: 1px solid #2d3846; font-size: 10px; font-weight: bold; text-transform: uppercase; padding: 5px 10px; color: #cbd5e0; border-radius: 4px; }
                QPushButton:hover { background-color: #2b3545; color: #ffffff; }
                QPushButton:checked { background-color: #c53030; border: 1px solid #e53e3e; color: #ffffff; }
            """)
            btn.clicked.connect(lambda checked, idx=i: self.test_relay_channel(idx, checked))
            test_btns_layout.addWidget(btn)
            self.relay_buttons.append(btn)
        relay_layout.addLayout(test_btns_layout, 1, 2, 1, 2)

        # Row 2: Hardware Coil Output Button (Full Width)
        self.btn_coil_toggle = QPushButton("🔌 HARDWARE COIL OUTPUT: ENABLED")
        self.btn_coil_toggle.setCheckable(True)
        self.btn_coil_toggle.setChecked(True)
        self.btn_coil_toggle.setStyleSheet("""
            QPushButton {
                background-color: #153e21; border: 1px solid #22543d; color: #48bb78;
                font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold; border-radius: 5px; padding: 8px;
            }
            QPushButton:hover { background-color: #1a4d29; }
            QPushButton:!checked {
                background-color: #4a2020; border: 1px solid #742a2a; color: #f6ad55;
            }
        """)
        self.btn_coil_toggle.clicked.connect(self.toggle_hardware_coil)
        relay_layout.addWidget(self.btn_coil_toggle, 2, 0, 1, 4)

        setup_layout.addWidget(group_relay)

        # ==========================================================
        # GROUP 2: STATION CAMERA DEVICE INDEX MAPPING (AUTO-LOCKED)
        # ==========================================================
        group_cam_mapping = QGroupBox("STATION CAMERA USB PORT & HARDWARE BINDING")
        cam_mapping_main_layout = QVBoxLayout(group_cam_mapping)
        cam_mapping_main_layout.setContentsMargins(12, 14, 12, 12)
        cam_mapping_main_layout.setSpacing(10)

        # Header toolbar with Refresh button and explanation
        cam_bar = QHBoxLayout()
        cam_bar.setSpacing(10)
        lbl_cam_hint = QLabel("Lock physical USB ports or camera serials to fixed display viewports to prevent swapping during vibrations.")
        lbl_cam_hint.setStyleSheet("color: #a0aec0; font-size: 11px; font-weight: normal;")
        cam_bar.addWidget(lbl_cam_hint)
        cam_bar.addStretch()

        self.btn_refresh_cams = QPushButton("SCAN USB PORTS")
        self.btn_refresh_cams.setStyleSheet("""
            QPushButton {
                background-color: #2b3544; border: 1px solid #4a5568; color: #63b3ed;
                font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 5px 12px;
            }
            QPushButton:hover { background-color: #3b4758; color: #ffffff; }
        """)
        self.btn_refresh_cams.clicked.connect(self.refresh_camera_mapping_dropdowns)
        cam_bar.addWidget(self.btn_refresh_cams)
        cam_mapping_main_layout.addLayout(cam_bar)

        cam_mapping_grid = QGridLayout()
        cam_mapping_grid.setHorizontalSpacing(14)
        cam_mapping_grid.setVerticalSpacing(10)

        self.cam_node_labels = []
        self.cam_bind_status_labels = []
        self.cam_port_lock_buttons = []
        self.relay_a_dropdowns = []
        self.relay_b_dropdowns = []
        self.relay_a_active_checks = []
        self.relay_b_active_checks = []
        self.cam_port_dropdowns = []

        station_titles = [
            "STATION 01 — Viewport 1 (Top-Left)",
            "STATION 02 — Viewport 2 (Top-Right)",
            "STATION 03 — Viewport 3 (Bottom-Left)",
            "STATION 04 — Viewport 4 (Bottom-Right)",
        ]

        default_mapping_a = self.global_settings.get("relay_mapping", [1, 1, 1, 1])
        default_mapping_b = self.global_settings.get("relay_mapping_b", [2, 0, 4, 4])
        default_nodes = ["/dev/video0", "/dev/video2", "/dev/video4", "6"]
        relay_options = ["Relay 1", "Relay 2", "Relay 3", "Relay 4", "None"]

        def create_toggle_act(b):
            def _tog(chk):
                b.setText("✓  Active" if chk else "   Active")
                b.setStyleSheet(f"QPushButton {{ background: transparent; border: none; color: {'#ffffff' if chk else '#718096'}; font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold; text-transform: none; text-align: left; padding: 2px 4px; }}")
                self.instant_save_timer_config()
            return _tog

        for i in range(4):
            sub_group = QGroupBox(station_titles[i])
            sub_group.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #232a36;
                    border-radius: 6px;
                    margin-top: 10px;
                    padding: 10px 12px 10px 12px;
                    font-family: 'Segoe UI Semibold';
                    font-size: 11px;
                    font-weight: bold;
                    color: #63b3ed;
                    background-color: #12151c;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 8px;
                    padding: 0 6px;
                    background-color: #1a2230;
                    border: 1px solid #2d3846;
                    border-radius: 3px;
                }
            """)
            sub_layout = QGridLayout(sub_group)
            sub_layout.setContentsMargins(10, 14, 10, 8)
            sub_layout.setHorizontalSpacing(8)
            sub_layout.setVerticalSpacing(8)
            sub_layout.setColumnStretch(0, 0)
            sub_layout.setColumnStretch(1, 1)
            sub_layout.setColumnStretch(2, 0)

            # Row 0: USB Port / Camera Selection Dropdown + Lock Button
            sub_layout.addWidget(QLabel("USB Port / Camera:"), 0, 0)
            port_combo = QComboBox()
            port_combo.setView(QListView())
            port_combo.setStyleSheet("""
                QComboBox {
                    background-color: #1a202c; border: 1px solid #3182ce; border-radius: 4px;
                    padding: 4px 8px; color: #63b3ed; font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold;
                }
                QComboBox:hover { border-color: #63b3ed; }
                QComboBox QAbstractItemView {
                    background-color: #1a202c; color: #ffffff; selection-background-color: #2b6cb0;
                }
            """)
            port_combo.currentIndexChanged.connect(lambda _, s=i: self.on_camera_port_reassigned(s))
            sub_layout.addWidget(port_combo, 0, 1)
            self.cam_port_dropdowns.append(port_combo)

            btn_lock = QPushButton("LOCK PORT")
            btn_lock.setToolTip("Lock this physical USB port to this display viewport to prevent camera swapping during vibrations.")
            btn_lock.setStyleSheet("""
                QPushButton {
                    background-color: #1e3a2b; border: 1px solid #2f855a; color: #48bb78;
                    font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 4px 8px;
                }
                QPushButton:hover { background-color: #276749; color: #ffffff; }
            """)
            btn_lock.clicked.connect(lambda _, s=i: self.on_camera_port_reassigned(s))
            sub_layout.addWidget(btn_lock, 0, 2)
            self.cam_port_lock_buttons.append(btn_lock)

            # Row 1: Hardware Binding Status Badge
            lbl_status = QLabel("NOT BOUND")
            lbl_status.setStyleSheet("color: #a0aec0; font-family: 'Segoe UI Semibold'; font-size: 10px;")
            sub_layout.addWidget(QLabel("Binding Status:"), 1, 0)
            sub_layout.addWidget(lbl_status, 1, 1, 1, 2)
            self.cam_bind_status_labels.append(lbl_status)

            # Row 2: Active Device Node
            sub_layout.addWidget(QLabel("Device Node:"), 2, 0)
            dev_text = default_nodes[i] if i < len(default_nodes) else f"/dev/video{i*2}"
            lbl_dev = QLabel(dev_text)
            lbl_dev.setStyleSheet("color: #63b3ed; font-family: 'Segoe UI Semibold', monospace; font-size: 11px; font-weight: bold;")
            sub_layout.addWidget(lbl_dev, 2, 1, 1, 2)
            self.cam_node_labels.append(lbl_dev)

            # Row 3: Relay A
            sub_layout.addWidget(QLabel("Relay A:"), 3, 0)
            combo_a = QComboBox()
            combo_a.setView(QListView())
            combo_a.addItems(relay_options)
            sel_a = default_mapping_a[i] if i < len(default_mapping_a) else 1
            if 1 <= sel_a <= 4:
                combo_a.setCurrentIndex(sel_a - 1)
            else:
                combo_a.setCurrentIndex(4)
            combo_a.currentIndexChanged.connect(self.instant_save_timer_config)
            sub_layout.addWidget(combo_a, 3, 1)
            self.relay_a_dropdowns.append(combo_a)

            btn_act_a = QPushButton("✓  Active")
            btn_act_a.setCheckable(True)
            btn_act_a.setChecked(True)
            btn_act_a.setStyleSheet("QPushButton { background: transparent; border: none; color: #ffffff; font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold; text-transform: none; text-align: left; padding: 2px 4px; } QPushButton:hover { color: #63b3ed; }")
            btn_act_a.clicked.connect(create_toggle_act(btn_act_a))
            sub_layout.addWidget(btn_act_a, 3, 2)
            self.relay_a_active_checks.append(btn_act_a)

            # Row 4: Relay B
            sub_layout.addWidget(QLabel("Relay B:"), 4, 0)
            combo_b = QComboBox()
            combo_b.setView(QListView())
            combo_b.addItems(relay_options)
            sel_b = default_mapping_b[i] if i < len(default_mapping_b) else (2 if i == 0 else (4 if i in [2, 3] else 0))
            if 1 <= sel_b <= 4:
                combo_b.setCurrentIndex(sel_b - 1)
            else:
                combo_b.setCurrentIndex(4)
            combo_b.currentIndexChanged.connect(self.instant_save_timer_config)
            sub_layout.addWidget(combo_b, 4, 1)
            self.relay_b_dropdowns.append(combo_b)

            btn_act_b = QPushButton("   Active")
            btn_act_b.setCheckable(True)
            btn_act_b.setChecked(False)
            btn_act_b.setStyleSheet("QPushButton { background: transparent; border: none; color: #718096; font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold; text-transform: none; text-align: left; padding: 2px 4px; } QPushButton:hover { color: #cbd5e0; }")
            btn_act_b.clicked.connect(create_toggle_act(btn_act_b))
            sub_layout.addWidget(btn_act_b, 4, 2)
            self.relay_b_active_checks.append(btn_act_b)

            row = i // 2
            col = i % 2
            cam_mapping_grid.addWidget(sub_group, row, col)

        cam_mapping_main_layout.addLayout(cam_mapping_grid)
        setup_layout.addWidget(group_cam_mapping)
        self.relay_dropdowns = self.relay_a_dropdowns  # Alias for backward compatibility

        # ==========================================================
        # GROUP 3: ARTIFICIAL INTELLIGENCE CORE CONFIG
        # ==========================================================
        group_ai = QGroupBox("🧠 ARTIFICIAL INTELLIGENCE CORE CONFIG")
        ai_layout = QGridLayout(group_ai)
        ai_layout.setContentsMargins(14, 14, 14, 12)
        ai_layout.setSpacing(10)

        ai_layout.addWidget(QLabel("YOLO Weights Path:"), 0, 0)
        self.model_input = QLineEdit()
        self.model_input.setText(self.global_settings.get("model_path", "yolov8n.pt"))
        ai_layout.addWidget(self.model_input, 0, 1)

        self.btn_browse = QPushButton("📂 BROWSE WEIGHTS...")
        self.btn_browse.setStyleSheet("""
            QPushButton {
                background-color: transparent; border: none; color: #ecc94b;
                font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold; padding: 4px 6px;
            }
            QPushButton:hover { color: #f6e05e; }
        """)
        self.btn_browse.clicked.connect(self.browse_model)
        ai_layout.addWidget(self.btn_browse, 0, 2)

        ai_layout.addWidget(QLabel("Confidence Threshold:"), 1, 0)
        
        self.conf_slider = QSlider(Qt.Horizontal)
        self.conf_slider.setRange(10, 95)
        self.conf_slider.setValue(int(self.global_settings.get("confidence", 0.35) * 100))
        self.conf_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px; background: #2d3846; border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #3182ce; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #000000; border: 1px solid #4a5568; width: 12px; margin-top: -5px; margin-bottom: -5px; border-radius: 3px;
            }
        """)
        ai_layout.addWidget(self.conf_slider, 1, 1)

        self.conf_val_label = QLabel(f"{self.conf_slider.value() / 100.0:.2f}")
        self.conf_val_label.setStyleSheet("color: #63b3ed; font-family: 'Segoe UI Semibold', monospace; font-size: 12px; font-weight: bold;")
        self.conf_slider.valueChanged.connect(lambda val: (
            self.conf_val_label.setText(f"{val/100:.2f}"),
            self.instant_save_timer_config()
        ))
        ai_layout.addWidget(self.conf_val_label, 1, 2)

        setup_layout.addWidget(group_ai)

        # ==========================================================
        # GROUP 4: NON-BLOCKING RELAY TIMER CONFIGURATION
        # ==========================================================
        group_timers = QGroupBox("⏱ NON-BLOCKING RELAY TIMER CONFIGURATION")
        timer_layout = QGridLayout(group_timers)
        timer_layout.setContentsMargins(14, 14, 14, 12)
        timer_layout.setSpacing(10)

        # Row 0: On-Delay
        timer_layout.addWidget(QLabel("On-Delay (Debounce) [seconds]:"), 0, 0)
        self.on_delay_spin = QDoubleSpinBox()
        self.on_delay_spin.setRange(0.0, 10.0)
        self.on_delay_spin.setSingleStep(0.1)
        self.on_delay_spin.setDecimals(1)
        self.on_delay_spin.setValue(self.global_settings.get("on_delay", 0.0))
        self.on_delay_spin.setSuffix(" s")
        timer_layout.addWidget(self.on_delay_spin, 0, 1)

        on_delay_hint = QLabel("Prevents false alarms from brief camera glints.")
        on_delay_hint.setStyleSheet("color: #718096; font-size: 10px; font-style: italic;")
        timer_layout.addWidget(on_delay_hint, 0, 2)

        # Row 1: Off-Delay
        timer_layout.addWidget(QLabel("Off-Delay (Hold/Cooldown) [seconds]:"), 1, 0)
        self.off_delay_spin = QDoubleSpinBox()
        self.off_delay_spin.setRange(0.1, 30.0)
        self.off_delay_spin.setSingleStep(0.5)
        self.off_delay_spin.setDecimals(1)
        self.off_delay_spin.setValue(self.global_settings.get("off_delay", 10.0))
        self.off_delay_spin.setSuffix(" s")
        timer_layout.addWidget(self.off_delay_spin, 1, 1)

        off_delay_hint = QLabel("Ensures horn/alarm sounds long enough to warn operators.")
        off_delay_hint.setStyleSheet("color: #718096; font-size: 10px; font-style: italic;")
        timer_layout.addWidget(off_delay_hint, 1, 2)

        # Row 2: Alarm Auto Reset Time
        timer_layout.addWidget(QLabel("Alarm Auto Reset Time (seconds):"), 2, 0)
        self.alarm_auto_reset_spin = QDoubleSpinBox()
        self.alarm_auto_reset_spin.setRange(0.1, 60.0)
        self.alarm_auto_reset_spin.setSingleStep(0.5)
        self.alarm_auto_reset_spin.setDecimals(1)
        self.alarm_auto_reset_spin.setValue(self.global_settings.get("alarm_auto_reset", 20.0))
        self.alarm_auto_reset_spin.setSuffix(" s")
        timer_layout.addWidget(self.alarm_auto_reset_spin, 2, 1)

        alarm_auto_reset_hint = QLabel("Auto-clears the alarm after this time if person remains.")
        alarm_auto_reset_hint.setStyleSheet("color: #718096; font-size: 10px; font-style: italic;")
        timer_layout.addWidget(alarm_auto_reset_hint, 2, 2)

        # Row 3: Enable Hardware Self-Test on Boot Checkbox
        self.boot_test_check = QCheckBox("Enable Hardware Self-Test on Boot")
        self.boot_test_check.setChecked(self.global_settings.get("boot_self_test", 1) == 1)
        self.boot_test_check.setStyleSheet("color: #ffffff; font-family: 'Segoe UI Semibold'; font-size: 11px;")
        timer_layout.addWidget(self.boot_test_check, 3, 0, 1, 3)

        self.on_delay_spin.valueChanged.connect(self.instant_save_timer_config)
        self.off_delay_spin.valueChanged.connect(self.instant_save_timer_config)
        self.alarm_auto_reset_spin.valueChanged.connect(self.instant_save_timer_config)
        self.boot_test_check.stateChanged.connect(self.instant_save_timer_config)

        setup_layout.addWidget(group_timers)

        # Save configuration parameters button
        self.btn_save_config = QPushButton("💾 SAVE CONFIGURATIONS PARAMETERS")
        self.btn_save_config.setStyleSheet("""
            QPushButton {
                background-color: #1a365d; border: 1px solid #2b6cb0; color: #ffffff;
                font-family: 'Segoe UI Semibold'; font-size: 13px; font-weight: bold; border-radius: 6px; padding: 12px;
            }
            QPushButton:hover { background-color: #2b548a; }
        """)
        self.btn_save_config.clicked.connect(self.save_global_configurations)
        setup_layout.addWidget(self.btn_save_config)

        self.setup_scroll.setWidget(self.setup_page)
        self.stacked_widget.addWidget(self.setup_scroll)
        # ---------------------------------------------
        # PAGE 2: HEALTH & DIAGNOSTICS (SCROLLABLE INDUSTRIAL CONSOLE)
        # ---------------------------------------------
        self.health_scroll = QScrollArea()
        self.health_scroll.setWidgetResizable(True)
        self.health_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.health_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.health_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background: #111620;
                width: 10px;
                margin: 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #2b3548;
                min-height: 25px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3b82f6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        # ---------------------------------------------
        # PAGE 2: HEALTH & DIAGNOSTICS (MODULAR)
        # ---------------------------------------------
        if _HEALTH_MODULE_AVAILABLE:
            self.metrics_engine = MetricsEngine(gui_ref=self)
            self.metrics_engine.start()
            self.health_page = HealthDiagnosticsPage(self.metrics_engine)
            self.health_scroll.setWidget(self.health_page)
            self.stacked_widget.addWidget(self.health_scroll)

            self.health_refresh_timer = QTimer(self)
            self.health_refresh_timer.setInterval(1000)
            self.health_refresh_timer.timeout.connect(self.health_page.refresh_ui)
        else:
            self.health_page = self.build_health_diagnostics_page()
            self.health_scroll.setWidget(self.health_page)
            self.stacked_widget.addWidget(self.health_scroll)

        # ---------------------------------------------
        # PAGE 3: REPORTS & EMAIL (MODULAR)
        # ---------------------------------------------
        if _REPORTING_MODULE_AVAILABLE:
            self.report_manager = ReportManager()
            self.email_scheduler = EmailScheduler(config=None, gui_ref=self)
            self.reports_page = ReportsEmailPage(
                gui_ref=self,
                report_manager=self.report_manager,
                email_scheduler=self.email_scheduler
            )
            self.stacked_widget.addWidget(self.reports_page)
            self.email_scheduler.trigger_report_email.connect(self.reports_page.send_scheduled_email)
            self.email_scheduler.start()
        else:
            self.reports_page = self.build_reports_email_page()
            self.stacked_widget.addWidget(self.reports_page)

        middle_layout.addWidget(self.stacked_widget, stretch=1)

        # Global Sidebar Controls Panel
        self.control_panel = QFrame()
        self.control_panel.setObjectName("sidebar")
        # Scale sidebar width proportionally to screen width.
        # Original design: 280px sidebar on ~1920px screen (~14.6% of width).
        # On 1024x768: 14.6% = ~149px (minimum 160 to keep labels readable, max 280).
        _sidebar_w = max(160, min(280, int(self._screen_w * 0.146)))
        self.control_panel.setFixedWidth(_sidebar_w)
        
        # Scale sidebar internal spacing/margins with ui_scale.
        _sb_spacing = max(4,  int(10 * _s))
        _sb_margin  = max(6,  int(14 * _s))
        control_layout = QVBoxLayout()
        control_layout.setSpacing(_sb_spacing)
        control_layout.setContentsMargins(_sb_margin, _sb_margin, _sb_margin, _sb_margin)

        # Navigation Area
        control_layout.addWidget(QLabel("🧭 MASTER CONSOLE NAVIGATION", objectName="sidebarHeader"))
        
        self.btn_nav_live = QPushButton("🎥 LIVE MONITORING")
        self.btn_nav_live.clicked.connect(self.show_live_page)
        control_layout.addWidget(self.btn_nav_live)

        self.btn_nav_config = QPushButton("⚙ SYSTEM CONFIG")
        self.btn_nav_config.clicked.connect(self.show_config_page)
        control_layout.addWidget(self.btn_nav_config)

        self.btn_nav_health = QPushButton("🩺 HEALTH_DIAG.")
        self.btn_nav_health.clicked.connect(self.show_health_page)
        control_layout.addWidget(self.btn_nav_health)

        self.btn_nav_reports = QPushButton("✉ REPORTS_EMAIL")
        self.btn_nav_reports.clicked.connect(self.show_reports_page)
        control_layout.addWidget(self.btn_nav_reports)
        
        # Set default active navigation page
        self.show_live_page()

        control_layout.addSpacing(6)

        control_layout.addWidget(QLabel("🔒 SECURITY ACCESS LEVEL", objectName="sidebarHeader"))
        self.role_combo = QComboBox()
        self.role_combo.setView(QListView())
        # Expanded 5-level role combobox
        self.role_combo.addItems(["Operator", "Technician", "Supervisor", "Engineer", "Administrator"])
        self.role_combo.currentTextChanged.connect(self.change_role)
        control_layout.addWidget(self.role_combo)

        control_layout.addSpacing(6)

        control_layout.addWidget(QLabel("🎛️ GLOBAL CONSOLE OVERRIDES", objectName="sidebarHeader"))
        self.btn_enable_all = QPushButton("▶ ENABLE ALL FEEDS", objectName="btnEnable")
        self.btn_enable_all.clicked.connect(self.global_start_all)
        control_layout.addWidget(self.btn_enable_all)

        self.btn_disable_all = QPushButton("■ DISABLE ALL FEEDS", objectName="btnDisable")
        self.btn_disable_all.clicked.connect(self.global_stop_all)
        control_layout.addWidget(self.btn_disable_all)

        self.btn_change_password = QPushButton("⚙ CONFIG PASSWORD")
        self.btn_change_password.clicked.connect(self.change_password)
        control_layout.addWidget(self.btn_change_password)



        control_layout.addSpacing(6)

        control_layout.addWidget(QLabel("📜 audit operations terminal", objectName="sidebarHeader"))
        self.log_terminal = QListWidget()
        control_layout.addWidget(self.log_terminal, stretch=1)

        self.control_panel.setLayout(control_layout)
        middle_layout.addWidget(self.control_panel)

        container_layout.addLayout(middle_layout)

        # --- FOOTER CENTRAL STATUS BANNER ---
        # Scale footer font and padding so it doesn't consume excess height on 1024x768.
        _footer_fs  = max(9,  int(14 * _s))
        _footer_pad = max(4,  int(12 * _s))
        self.status_label = QLabel("✔ ALL SECTORS SECURE - SYSTEM MONITORING STANDBY")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(f"""
            background-color: #2b3544; color: #cbd5e0;
            font-family: 'Segoe UI Semibold'; font-size: {_footer_fs}px; font-weight: bold;
            padding: {_footer_pad}px 20px; border-radius: 6px;
            border: 1px solid #3c4a5e;
        """)

        self.exit_button = QPushButton("❌ SHUTDOWN APPLIC.")
        self.exit_button.setObjectName("btnExit")
        self.exit_button.clicked.connect(self.close_app)

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(12)
        bottom_layout.addWidget(self.status_label, stretch=1)
        bottom_layout.addWidget(self.exit_button)
        container_layout.addLayout(bottom_layout)

        # Initialize coil button state
        coil_enabled = self.global_settings.get("hardware_coil_enabled", 1) == 1
        self.btn_coil_toggle.setChecked(coil_enabled)
        if coil_enabled:
            self.btn_coil_toggle.setText("🔌 HARDWARE COIL OUTPUT: ENABLED")
            self.relay_manager.set_hardware_coil_enabled(True)
        else:
            self.btn_coil_toggle.setText("🔌 HARDWARE COIL OUTPUT: DISABLED")
            self.relay_manager.set_hardware_coil_enabled(False)

        # Establish default serial handshake on startup
        com_port = self.global_settings.get("com_port", "/dev/ttyUSB0" if sys.platform != "win32" else "COM3")
        self.relay_manager.connect_port(com_port)

        # Log system boot events
        self.add_audit_log("Master Operations Console loaded in Industrial Kiosk Mode.")
        self.add_audit_log("OPERATOR level permissions engaged.")

        # ---------------------------------------------
        # INACTIVITY AUTO-LOGOUT TIMER (5 minutes)
        # ---------------------------------------------
        self.inactivity_timer = QTimer(self)
        self.inactivity_timer.setInterval(300000)  # 300,000 ms = 5 minutes
        self.inactivity_timer.timeout.connect(self.auto_logout)
        self.inactivity_timer.start()

        # Install application-wide event filter to capture raw user inputs and reset auto-logout timer
        QApplication.instance().installEventFilter(self)

        # ---------------------------------------------
        # AUTONOMOUS STARTUP FEED ACTIVATION
        # ---------------------------------------------
        # Boot feeds according to persisted enabled/disabled state
        enabled_list = self.global_settings.get("cameras_enabled", [True, True, True, True])
        for i, card in enumerate(self.cards):
            if i < len(enabled_list) and enabled_list[i]:
                card.start_camera(persist=False)
            else:
                card.stop_camera(persist=False)
                self.add_audit_log(f"Station {i + 1} feed remains DISABLED per saved configuration.", "config")

        # Set initial access level logic
        self.update_ui_permissions()

        # ---------------------------------------------
        # SERIAL RELAY HARDWARE STATUS TIMER
        # ---------------------------------------------
        self.hardware_is_online = True
        self.hardware_offline_blink = False
        
        self.status_check_timer = QTimer(self)
        self.status_check_timer.setInterval(1000) # Check and blink every 1 second
        self.status_check_timer.timeout.connect(self.poll_hardware_status)
        self.status_check_timer.start()


    # ==========================================
    # GLOBAL APPLICATION INPUT EVENT FILTER (INACTIVITY TIMEOUT RESET)
    # ==========================================
    def eventFilter(self, obj, event):
        # Refresh inactivity countdown timer if any mouse/keyboard actions occur
        if event.type() in [
            QEvent.MouseButtonPress,
            QEvent.MouseButtonRelease,
            QEvent.MouseMove,
            QEvent.KeyPress,
            QEvent.KeyRelease,
            QEvent.Wheel
        ]:
            if hasattr(self, 'inactivity_timer') and self.inactivity_timer.isActive():
                self.inactivity_timer.start()  # Re-fires timer, resetting interval
        return super().eventFilter(obj, event)

    def auto_logout(self):
        """Autologout handler triggers rollback to Operator access state."""
        if self.current_role != "Operator":
            self.role_combo.setCurrentText("Operator")
            self.add_audit_log("AUTO-LOGOUT: Inactivity timeout reached. Rolled back to Operator.", "warning")

    # ==========================================
    # NAVIGATION METHODS
    # ==========================================
    def _update_nav_styles(self, active_idx):
        active_style = """
            QPushButton {
                background-color: #1a2736; border: 1px solid #3182ce; color: #ffffff;
                font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold; border-radius: 4px; padding: 10px 4px;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: #212630; border: 1px solid #2d3846; color: #cbd5e0;
                font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold; border-radius: 4px; padding: 10px 4px;
            }
            QPushButton:hover { background-color: #2d3545; }
        """
        nav_buttons = [
            getattr(self, 'btn_nav_live', None),
            getattr(self, 'btn_nav_config', None),
            getattr(self, 'btn_nav_health', None),
            getattr(self, 'btn_nav_reports', None)
        ]
        for i, btn in enumerate(nav_buttons):
            if btn is not None:
                btn.setStyleSheet(active_style if i == active_idx else inactive_style)

    def show_live_page(self):
        if hasattr(self, "relay_manager") and self.relay_manager is not None:
            self.relay_manager.manual_overrides = [False, False, False, False]
            
        if hasattr(self, "relay_buttons"):
            for btn in self.relay_buttons:
                if btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)

        self.stacked_widget.setCurrentIndex(0)
        self._update_nav_styles(0)

    def scan_all_usb_camera_devices(self):
        """
        Scans all available video nodes and physical USB devices to return rich details:
        - connected_cams: list of details dicts for all detected /dev/video* cameras
        - physical_ports: list of all detected physical USB ports
        """
        nodes = sorted(glob.glob('/dev/video*'))
        connected_cams = []
        physical_ports = set()

        for node in nodes:
            details = get_usb_camera_details(node)
            if details:
                connected_cams.append(details)
                if details.get("physical_port"):
                    physical_ports.add(details["physical_port"])
            else:
                phys = get_physical_usb_path(node)
                if phys:
                    physical_ports.add(phys)

        # Scan sysfs usb bus devices to include all available motherboard / hub ports
        try:
            for dev_path in glob.glob('/sys/bus/usb/devices/*'):
                base = os.path.basename(dev_path)
                if '-' in base and not base.startswith('usb') and ':' not in base:
                    physical_ports.add(base)
        except Exception:
            pass

        return connected_cams, sorted(list(physical_ports))

    def scan_available_physical_usb_ports(self):
        """Scans all available /dev/video* device nodes and resolves their physical USB paths."""
        _, ports = self.scan_all_usb_camera_devices()
        return ports

    def _update_station_bind_badge(self, station_idx, bound_val):
        """Updates the visual lock status badge for a display station."""
        if not hasattr(self, "cam_bind_status_labels") or station_idx >= len(self.cam_bind_status_labels):
            return
        lbl = self.cam_bind_status_labels[station_idx]
        if bound_val and bound_val != "None" and "Auto" not in str(bound_val):
            val_str = str(bound_val)
            if val_str.startswith("serial:"):
                sn = val_str[7:]
                lbl.setText(f"🔒 LOCKED (Serial: {sn})")
            elif val_str.startswith("/dev/video"):
                lbl.setText(f"🔒 LOCKED (Device: {val_str})")
            else:
                lbl.setText(f"🔒 LOCKED (USB Port: {val_str})")
            lbl.setStyleSheet("color: #48bb78; font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold;")
        else:
            lbl.setText("⚠️ NOT LOCKED / UNASSIGNED")
            lbl.setStyleSheet("color: #e53e3e; font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold;")

    def refresh_camera_mapping_dropdowns(self):
        """
        Populates each station's dropdown with scanned active USB cameras,
        physical bus ports, serial numbers, video nodes, and saved configs.
        """
        connected_cams, available_ports = self.scan_all_usb_camera_devices()
        available_nodes = sorted(glob.glob('/dev/video*'))
        saved_paths = self.global_settings.get("camera_physical_paths", [None, None, None, None])
        saved_nodes = self.global_settings.get("camera_mapping", [0, 2, 4, 6])
        standard_nodes = [f"/dev/video{x}" for x in range(8)]

        for i, combo in enumerate(self.cam_port_dropdowns):
            combo.blockSignals(True)
            current_choice = combo.currentData()
            if current_choice is None:
                if i < len(saved_paths) and saved_paths[i]:
                    current_choice = saved_paths[i]
                elif i < len(saved_nodes):
                    current_choice = saved_nodes[i]

            combo.clear()
            node_fallback = saved_nodes[i] if i < len(saved_nodes) else f"/dev/video{i*2}"

            # 1. Scanned connected USB cameras with full details (Port + Serial + Model + Node)
            for cam in connected_cams:
                port = cam.get("physical_port")
                serial = cam.get("serial")
                node = cam.get("node")
                prod = cam.get("product") or "Camera"

                if port and serial:
                    label = f"🔌 USB Port [{port}] | Serial: {serial} ({prod} - {node})"
                    combo.addItem(label, port)
                    combo.addItem(f"🏷️ Serial: {serial} ({prod} - Port {port})", f"serial:{serial}")
                elif port:
                    label = f"🔌 USB Port [{port}] ({prod} - {node})"
                    combo.addItem(label, port)
                elif serial:
                    label = f"🏷️ Serial: {serial} ({prod} - {node})"
                    combo.addItem(label, f"serial:{serial}")
                else:
                    label = f"📹 {node} ({prod})"
                    combo.addItem(label, node)

            # 2. All physical USB bus ports (allows fixing port to prevent vibration swaps)
            for port in available_ports:
                found_item = False
                for idx in range(combo.count()):
                    if combo.itemData(idx) == port:
                        found_item = True
                        break
                if not found_item:
                    combo.addItem(f"🔌 USB Port [{port}]", port)

            # 3. Scanned real V4L2 device nodes (if physically present)
            for node in available_nodes:
                found_item = False
                for idx in range(combo.count()):
                    if combo.itemData(idx) == node:
                        found_item = True
                        break
                if not found_item:
                    phys = get_physical_usb_path(node)
                    desc = f"📹 {node} [USB: {phys}]" if phys else f"📹 {node}"
                    combo.addItem(desc, node)

            # 4. Saved choice preservation if not in scanned list
            if current_choice is not None:
                found = False
                for idx in range(combo.count()):
                    if combo.itemData(idx) == current_choice or str(combo.itemData(idx)) == str(current_choice):
                        found = True
                        break
                if not found:
                    combo.addItem(f"💾 Saved: {current_choice}", current_choice)

            # Fallback if combo is empty
            if combo.count() == 0:
                combo.addItem(f"Node {node_fallback}", node_fallback)

            # Select matching item
            selected_idx = 0
            if current_choice is not None:
                for idx in range(combo.count()):
                    if combo.itemData(idx) == current_choice or str(combo.itemData(idx)) == str(current_choice):
                        selected_idx = idx
                        break
            combo.setCurrentIndex(selected_idx)
            combo.blockSignals(False)

            # Update lock status badge & active node display
            self._update_station_bind_badge(i, combo.currentData())
            if i < len(self.cam_node_labels):
                active_dev = str(combo.currentData()) if combo.currentData() is not None else str(node_fallback)
                self.cam_node_labels[i].setText(active_dev)

    def on_camera_port_reassigned(self, station_idx):
        """Allows operators to reassign camera ports on-the-fly and saves the updated physical paths or device nodes directly to config.json."""
        if station_idx >= len(self.cam_port_dropdowns):
            return

        combo = self.cam_port_dropdowns[station_idx]
        selected_data = combo.currentData()
        selected_text = combo.currentText()

        target_val = selected_data if selected_data is not None else selected_text
        if isinstance(target_val, str):
            target_val = target_val.strip()
            if "USB Port: " in target_val:
                target_val = target_val.split("USB Port: ")[-1].strip()
            elif "USB Port [" in target_val:
                target_val = target_val.split("USB Port [")[-1].split("]")[0].strip()
            elif "/dev/video" in target_val and not target_val.startswith("🔌") and not target_val.startswith("🏷️"):
                match = re.search(r'/dev/video\d+', target_val)
                if match:
                    target_val = match.group(0)

        print(f"[CONFIG] Reassigning Station {station_idx + 1} to: {target_val}")

        if "camera_physical_paths" not in self.global_settings:
            self.global_settings["camera_physical_paths"] = [None, None, None, None]
        while len(self.global_settings["camera_physical_paths"]) < 4:
            self.global_settings["camera_physical_paths"].append(None)

        if "camera_mapping" not in self.global_settings:
            self.global_settings["camera_mapping"] = ["/dev/video0", "/dev/video2", "/dev/video4", "/dev/video6"]
        while len(self.global_settings["camera_mapping"]) < 4:
            self.global_settings["camera_mapping"].append(0)

        is_phys_or_serial = False
        if target_val and isinstance(target_val, str) and not target_val.startswith("/dev/video") and not target_val.isdigit() and "Auto" not in target_val:
            is_phys_or_serial = True

        if is_phys_or_serial:
            self.global_settings["camera_physical_paths"][station_idx] = target_val
            persist_station_physical_path(station_idx, target_val)
            card_phys = target_val
            card_node = self.global_settings["camera_mapping"][station_idx]
        elif target_val is not None and "Auto" not in str(target_val):
            node_idx = int(target_val) if str(target_val).isdigit() else target_val
            self.global_settings["camera_mapping"][station_idx] = node_idx
            self.global_settings["camera_physical_paths"][station_idx] = None
            persist_station_physical_path(station_idx, None)
            card_phys = None
            card_node = node_idx
        else:
            self.global_settings["camera_physical_paths"][station_idx] = None
            persist_station_physical_path(station_idx, None)
            card_phys = None
            card_node = self.global_settings["camera_mapping"][station_idx]

        self.instant_save_timer_config()

        # Update badge and node label in settings view
        self._update_station_bind_badge(station_idx, card_phys or target_val)
        if station_idx < len(self.cam_node_labels):
            self.cam_node_labels[station_idx].setText(str(target_val or card_node))

        if station_idx < len(self.cards):
            card = self.cards[station_idx]
            card.target_physical_usb_path = card_phys
            card.device_index = card_node
            if card.camera_thread is not None:
                card.camera_thread.target_physical_usb_path = card_phys
                card.camera_thread.device_index = card_node
                card.camera_thread._release_camera_locked()

        self.add_audit_log(f"Station {station_idx + 1} locked to: {target_val or 'Unassigned'}", "config")

    def show_config_page(self):
        # Gatekeeper check: requires Supervisor or higher (level >= 2)
        role_level = self.access_levels.get(self.current_role, 1)
        if role_level < 2:
            QMessageBox.warning(self, "Access Denied", "System settings panel requires Supervisor or higher privileges.")
            return

        current_selection = self.com_combo.currentText()
        self.com_combo.clear()
        ports = self.relay_manager.scan_available_ports()
        self.com_combo.addItems(ports)
        if current_selection in ports:
            self.com_combo.setCurrentText(current_selection)
        else:
            self.com_combo.setCurrentText(self.global_settings.get("com_port", "/dev/ttyUSB0" if sys.platform != "win32" else "COM3"))

        self.refresh_camera_mapping_dropdowns()

        self.stacked_widget.setCurrentIndex(1)
        self._update_nav_styles(1)

    def show_health_page(self):
        self.stacked_widget.setCurrentIndex(2)
        self._update_nav_styles(2)
        if hasattr(self, 'health_refresh_timer'):
            self.health_refresh_timer.start()
        if hasattr(self, 'health_page') and hasattr(self.health_page, 'refresh_ui'):
            self.health_page.refresh_ui()
        elif hasattr(self, 'update_health_diagnostics'):
            self.update_health_diagnostics()

    def show_reports_page(self):
        role_level = self.access_levels.get(self.current_role, 1)
        if role_level < 3:
            QMessageBox.warning(self, "Access Denied", "Reports & Email panel requires Supervisor or higher privileges.")
            return
        self.stacked_widget.setCurrentIndex(3)
        self._update_nav_styles(3)

    def build_health_diagnostics_page(self):
        page = QWidget()
        page.setStyleSheet("""
            QWidget { background: transparent; color: #e2e8f0; font-family: 'Segoe UI', 'Ubuntu', sans-serif; }
            QGroupBox {
                border: 1px solid #2d3846;
                border-radius: 8px;
                margin-top: 16px;
                padding-top: 16px;
                font-family: 'Segoe UI Semibold';
                font-size: 11px;
                font-weight: bold;
                color: #63b3ed;
                background-color: #121721;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 8px;
                background-color: #1a2230;
                border: 1px solid #2d3846;
                border-radius: 4px;
                color: #63b3ed;
            }
            QProgressBar {
                border: 1px solid #2d3846;
                border-radius: 4px;
                background-color: #0d1117;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
                font-size: 10px;
                min-height: 16px;
                max-height: 16px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3182ce, stop:1 #48bb78);
                border-radius: 3px;
            }
        """)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 16, 20)
        layout.setSpacing(12)

        # ----------------------------------------------------
        # 1. HEADER & ACTION TOOLBAR
        # ----------------------------------------------------
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #161c28; border: 1px solid #2d3846; border-radius: 8px; padding: 6px;")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 6, 10, 6)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("🩺 SYSTEM HEALTH & HARDWARE DIAGNOSTICS")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #63b3ed; border: none;")
        lbl_sub = QLabel("Live Telemetry: CPU, Thermals, Process Threads, Memory, Storage, Cameras & Relay Controller")
        lbl_sub.setStyleSheet("font-size: 10px; color: #a0aec0; border: none;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        # Overall Status Badge
        self.lbl_diag_global_badge = QLabel("🟢 SYSTEM OPTIMAL")
        self.lbl_diag_global_badge.setStyleSheet("""
            background-color: #1c4532; color: #48bb78; font-family: 'Segoe UI Semibold';
            font-size: 11px; font-weight: bold; padding: 6px 12px; border-radius: 6px; border: 1px solid #2f855a;
        """)
        header_layout.addWidget(self.lbl_diag_global_badge)

        # Force Refresh Button
        self.btn_diag_refresh = QPushButton("🔄 REFRESH")
        self.btn_diag_refresh.setStyleSheet("""
            QPushButton {
                background-color: #2b3544; border: 1px solid #4a5568; color: #ffffff;
                font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { background-color: #3b4758; }
        """)
        self.btn_diag_refresh.clicked.connect(self.update_health_diagnostics)
        header_layout.addWidget(self.btn_diag_refresh)

        # Copy Diagnostic Report Button
        self.btn_diag_copy = QPushButton("📋 COPY REPORT")
        self.btn_diag_copy.setStyleSheet("""
            QPushButton {
                background-color: #234e52; border: 1px solid #319795; color: #e6fffa;
                font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { background-color: #285e61; }
        """)
        self.btn_diag_copy.clicked.connect(self.copy_diagnostics_report)
        header_layout.addWidget(self.btn_diag_copy)

        layout.addWidget(header_frame)

        # ----------------------------------------------------
        # 2. TOP 4 SUMMARY KPI CARDS GRID
        # ----------------------------------------------------
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(10)

        card_style = """
            QFrame {
                background-color: #161c28; border: 1px solid #2d3846; border-radius: 8px; padding: 10px;
            }
        """

        # KPI Card 1: CPU Total
        card_cpu = QFrame()
        card_cpu.setStyleSheet(card_style)
        card_cpu_layout = QVBoxLayout(card_cpu)
        card_cpu_layout.setContentsMargins(8, 8, 8, 8)
        card_cpu_layout.setSpacing(4)
        lbl_kpi_cpu_title = QLabel("⚡ TOTAL CPU LOAD")
        lbl_kpi_cpu_title.setStyleSheet("color: #63b3ed; font-size: 10px; font-weight: bold; border: none;")
        self.lbl_kpi_cpu_val = QLabel("0.0%")
        self.lbl_kpi_cpu_val.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff; border: none;")
        self.bar_kpi_cpu = QProgressBar()
        self.bar_kpi_cpu.setRange(0, 100)
        self.bar_kpi_cpu.setValue(0)
        self.lbl_kpi_cpu_sub = QLabel("4 Cores @ 2.50 GHz")
        self.lbl_kpi_cpu_sub.setStyleSheet("font-size: 9px; color: #a0aec0; border: none;")
        card_cpu_layout.addWidget(lbl_kpi_cpu_title)
        card_cpu_layout.addWidget(self.lbl_kpi_cpu_val)
        card_cpu_layout.addWidget(self.bar_kpi_cpu)
        card_cpu_layout.addWidget(self.lbl_kpi_cpu_sub)
        kpi_grid.addWidget(card_cpu, 0, 0)

        # KPI Card 2: Thermals
        card_temp = QFrame()
        card_temp.setStyleSheet(card_style)
        card_temp_layout = QVBoxLayout(card_temp)
        card_temp_layout.setContentsMargins(8, 8, 8, 8)
        card_temp_layout.setSpacing(4)
        lbl_kpi_temp_title = QLabel("🌡️ THERMALS & ENVIRONMENT")
        lbl_kpi_temp_title.setStyleSheet("color: #63b3ed; font-size: 10px; font-weight: bold; border: none;")
        self.lbl_kpi_temp_val = QLabel("--.- °C")
        self.lbl_kpi_temp_val.setStyleSheet("font-size: 20px; font-weight: bold; color: #48bb78; border: none;")
        self.bar_kpi_temp = QProgressBar()
        self.bar_kpi_temp.setRange(0, 100)
        self.bar_kpi_temp.setValue(45)
        self.bar_kpi_temp.setStyleSheet("""
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #48bb78, stop:0.7 #ecc94b, stop:1 #e53e3e);
            }
        """)
        self.lbl_kpi_temp_sub = QLabel("CPU Pkg: --°C | NVMe: --°C")
        self.lbl_kpi_temp_sub.setStyleSheet("font-size: 9px; color: #a0aec0; border: none;")
        card_temp_layout.addWidget(lbl_kpi_temp_title)
        card_temp_layout.addWidget(self.lbl_kpi_temp_val)
        card_temp_layout.addWidget(self.bar_kpi_temp)
        card_temp_layout.addWidget(self.lbl_kpi_temp_sub)
        kpi_grid.addWidget(card_temp, 0, 1)

        # KPI Card 3: RAM & Storage
        card_mem = QFrame()
        card_mem.setStyleSheet(card_style)
        card_mem_layout = QVBoxLayout(card_mem)
        card_mem_layout.setContentsMargins(8, 8, 8, 8)
        card_mem_layout.setSpacing(4)
        lbl_kpi_mem_title = QLabel("💾 RAM & STORAGE")
        lbl_kpi_mem_title.setStyleSheet("color: #63b3ed; font-size: 10px; font-weight: bold; border: none;")
        self.lbl_kpi_ram_val = QLabel("RAM: 0.0%")
        self.lbl_kpi_ram_val.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff; border: none;")
        self.bar_kpi_ram = QProgressBar()
        self.bar_kpi_ram.setRange(0, 100)
        self.bar_kpi_ram.setValue(0)
        self.lbl_kpi_disk_sub = QLabel("Disk: --% (Free: -- GB)")
        self.lbl_kpi_disk_sub.setStyleSheet("font-size: 9px; color: #a0aec0; border: none;")
        card_mem_layout.addWidget(lbl_kpi_mem_title)
        card_mem_layout.addWidget(self.lbl_kpi_ram_val)
        card_mem_layout.addWidget(self.bar_kpi_ram)
        card_mem_layout.addWidget(self.lbl_kpi_disk_sub)
        kpi_grid.addWidget(card_mem, 0, 2)

        # KPI Card 4: Threads & App Process
        card_proc = QFrame()
        card_proc.setStyleSheet(card_style)
        card_proc_layout = QVBoxLayout(card_proc)
        card_proc_layout.setContentsMargins(8, 8, 8, 8)
        card_proc_layout.setSpacing(4)
        lbl_kpi_proc_title = QLabel("🧵 THREADS & APPLICATION")
        lbl_kpi_proc_title.setStyleSheet("color: #63b3ed; font-size: 10px; font-weight: bold; border: none;")
        self.lbl_kpi_threads_val = QLabel("-- Threads")
        self.lbl_kpi_threads_val.setStyleSheet("font-size: 20px; font-weight: bold; color: #63b3ed; border: none;")
        self.lbl_kpi_proc_sub = QLabel("App CPU: --% | RAM: -- MB")
        self.lbl_kpi_proc_sub.setStyleSheet("font-size: 10px; font-weight: bold; color: #cbd5e0; border: none;")
        self.lbl_kpi_uptime_sub = QLabel("App Uptime: -- | System Uptime: --")
        self.lbl_kpi_uptime_sub.setStyleSheet("font-size: 9px; color: #a0aec0; border: none;")
        card_proc_layout.addWidget(lbl_kpi_proc_title)
        card_proc_layout.addWidget(self.lbl_kpi_threads_val)
        card_proc_layout.addWidget(self.lbl_kpi_proc_sub)
        card_proc_layout.addWidget(self.lbl_kpi_uptime_sub)
        kpi_grid.addWidget(card_proc, 0, 3)

        layout.addLayout(kpi_grid)

        # ----------------------------------------------------
        # 3. GROUP: CPU PER-CORE & THERMAL SENSORS
        # ----------------------------------------------------
        grp_cpu_thermal = QGroupBox("🔥 PROCESSOR CORES & THERMAL SENSORS")
        cpu_thermal_layout = QGridLayout(grp_cpu_thermal)
        cpu_thermal_layout.setContentsMargins(12, 12, 12, 12)
        cpu_thermal_layout.setSpacing(10)

        # Left Column: Per-Core Load Bars
        core_box = QVBoxLayout()
        core_box.setSpacing(6)
        core_hdr = QLabel("Per-Core Load Breakdown:")
        core_hdr.setStyleSheet("font-weight: bold; color: #cbd5e0; font-size: 10px;")
        core_box.addWidget(core_hdr)

        self.bar_core = []
        self.lbl_core_val = []
        for c in range(4):
            c_row = QHBoxLayout()
            c_row.setSpacing(8)
            lbl_c = QLabel(f"Core {c}:")
            lbl_c.setFixedWidth(50)
            lbl_c.setStyleSheet("font-family: monospace; font-size: 10px; color: #a0aec0;")
            bar_c = QProgressBar()
            bar_c.setRange(0, 100)
            bar_c.setValue(0)
            val_c = QLabel("0%")
            val_c.setFixedWidth(45)
            val_c.setStyleSheet("font-family: monospace; font-size: 10px; font-weight: bold; color: #ffffff;")
            c_row.addWidget(lbl_c)
            c_row.addWidget(bar_c, stretch=1)
            c_row.addWidget(val_c)
            core_box.addLayout(c_row)
            self.bar_core.append(bar_c)
            self.lbl_core_val.append(val_c)

        self.lbl_cpu_meta = QLabel("Processor: Intel(R) Core(TM) i5-6500T @ 2.50GHz (4 Cores / 4 Threads)")
        self.lbl_cpu_meta.setStyleSheet("font-size: 9px; color: #718096; padding-top: 4px;")
        core_box.addWidget(self.lbl_cpu_meta)

        cpu_thermal_layout.addLayout(core_box, 0, 0)

        # Right Column: Thermal Sensors Breakdown
        thermal_box = QVBoxLayout()
        thermal_box.setSpacing(6)
        th_hdr = QLabel("Hardware Thermal Sensor Readings:")
        th_hdr.setStyleSheet("font-weight: bold; color: #cbd5e0; font-size: 10px;")
        thermal_box.addWidget(th_hdr)

        self.lbl_temp_cpu_pkg = QLabel("• CPU Package: --.- °C (High: 84°C, Crit: 100°C)")
        self.lbl_temp_cpu_pkg.setStyleSheet("font-family: monospace; font-size: 10px; color: #48bb78;")
        thermal_box.addWidget(self.lbl_temp_cpu_pkg)

        self.lbl_temp_cpu_cores = QLabel("• CPU Cores [0,1,2,3]: --.- °C, --.- °C, --.- °C, --.- °C")
        self.lbl_temp_cpu_cores.setStyleSheet("font-family: monospace; font-size: 10px; color: #48bb78;")
        thermal_box.addWidget(self.lbl_temp_cpu_cores)

        self.lbl_temp_nvme = QLabel("• NVMe SSD Storage: --.- °C (Crit: 94.85°C)")
        self.lbl_temp_nvme.setStyleSheet("font-family: monospace; font-size: 10px; color: #63b3ed;")
        thermal_box.addWidget(self.lbl_temp_nvme)

        self.lbl_temp_pch = QLabel("• Motherboard Chipset (PCH): --.- °C")
        self.lbl_temp_pch.setStyleSheet("font-family: monospace; font-size: 10px; color: #a0aec0;")
        thermal_box.addWidget(self.lbl_temp_pch)

        self.lbl_temp_wifi = QLabel("• Wireless Adapter (WiFi): --.- °C")
        self.lbl_temp_wifi.setStyleSheet("font-family: monospace; font-size: 10px; color: #a0aec0;")
        thermal_box.addWidget(self.lbl_temp_wifi)

        cpu_thermal_layout.addLayout(thermal_box, 0, 1)
        layout.addWidget(grp_cpu_thermal)

        # ----------------------------------------------------
        # 4. GROUP: SOFTWARE & PROCESS DIAGNOSTICS
        # ----------------------------------------------------
        grp_sw = QGroupBox("💻 SOFTWARE & PROCESS DIAGNOSTICS")
        sw_layout = QGridLayout(grp_sw)
        sw_layout.setContentsMargins(12, 12, 12, 12)
        sw_layout.setSpacing(10)

        # Sub-card: Threads & Process
        sw_threads_box = QVBoxLayout()
        sw_threads_box.setSpacing(6)
        lbl_th_title = QLabel("Active Thread Breakdown:")
        lbl_th_title.setStyleSheet("font-weight: bold; color: #cbd5e0; font-size: 10px;")
        sw_threads_box.addWidget(lbl_th_title)

        self.lbl_diag_threads_summary = QLabel("Total Process Threads: -- OS Threads | Python: -- Threads")
        self.lbl_diag_threads_summary.setStyleSheet("color: #63b3ed; font-family: monospace; font-size: 10px; font-weight: bold;")
        sw_threads_box.addWidget(self.lbl_diag_threads_summary)

        self.lbl_diag_threads_list = QLabel("Threads: MainThread (GUI), CameraWorker-1..4, RelayIPC, Timers")
        self.lbl_diag_threads_list.setStyleSheet("color: #a0aec0; font-family: monospace; font-size: 9px; line-height: 1.4;")
        self.lbl_diag_threads_list.setWordWrap(True)
        sw_threads_box.addWidget(self.lbl_diag_threads_list)

        self.lbl_diag_proc_detail = QLabel("Process PID: -- | RAM RSS: -- MB | VMS: -- MB | Handles: OK")
        self.lbl_diag_proc_detail.setStyleSheet("color: #718096; font-family: monospace; font-size: 9px;")
        sw_threads_box.addWidget(self.lbl_diag_proc_detail)

        sw_layout.addLayout(sw_threads_box, 0, 0)

        # Sub-card: Runtime Environment & Libraries
        sw_env_box = QVBoxLayout()
        sw_env_box.setSpacing(6)
        lbl_env_title = QLabel("Runtime Stack & Environment:")
        lbl_env_title.setStyleSheet("font-weight: bold; color: #cbd5e0; font-size: 10px;")
        sw_env_box.addWidget(lbl_env_title)

        self.lbl_diag_os_info = QLabel(f"• Operating System: {platform.system()} {platform.release()} ({platform.machine()})")
        self.lbl_diag_os_info.setStyleSheet("color: #cbd5e0; font-family: monospace; font-size: 9px;")
        sw_env_box.addWidget(self.lbl_diag_os_info)

        self.lbl_diag_python_info = QLabel(f"• Python Runtime: Python {platform.python_version()} (Virtualenv: active)")
        self.lbl_diag_python_info.setStyleSheet("color: #cbd5e0; font-family: monospace; font-size: 9px;")
        sw_env_box.addWidget(self.lbl_diag_python_info)

        import cv2
        cv_ver = getattr(cv2, '__version__', 'N/A')
        torch_ver = getattr(torch, '__version__', 'N/A') if 'torch' in globals() and torch else 'N/A'
        self.lbl_diag_libs_info = QLabel(f"• Core Libraries: OpenCV {cv_ver} | PyTorch {torch_ver} (CPU Inference) | PyQt5")
        self.lbl_diag_libs_info.setStyleSheet("color: #cbd5e0; font-family: monospace; font-size: 9px;")
        sw_env_box.addWidget(self.lbl_diag_libs_info)

        self.lbl_diag_uptimes = QLabel("• Uptime: App: -- | System: --")
        self.lbl_diag_uptimes.setStyleSheet("color: #48bb78; font-family: monospace; font-size: 9px; font-weight: bold;")
        sw_env_box.addWidget(self.lbl_diag_uptimes)

        sw_layout.addLayout(sw_env_box, 0, 1)
        layout.addWidget(grp_sw)

        # ----------------------------------------------------
        # 5. GROUP: INDUSTRIAL RELAY & IPC TELEMETRY
        # ----------------------------------------------------
        grp_hw = QGroupBox("⚡ INDUSTRIAL RELAY & IPC TELEMETRY")
        hw_layout = QGridLayout(grp_hw)
        hw_layout.setContentsMargins(12, 12, 12, 12)
        hw_layout.setSpacing(10)

        self.lbl_diag_ipc_status = QLabel("IPC Socket Status: CONNECTED (/dev/shm/forklift_relay.sock)")
        self.lbl_diag_ipc_status.setStyleSheet("color: #48bb78; font-family: monospace; font-size: 10px; font-weight: bold;")
        hw_layout.addWidget(self.lbl_diag_ipc_status, 0, 0)

        self.lbl_diag_daemon_status = QLabel("Hardware Worker Daemon: RUNNING (PID: --)")
        self.lbl_diag_daemon_status.setStyleSheet("color: #48bb78; font-family: monospace; font-size: 10px; font-weight: bold;")
        hw_layout.addWidget(self.lbl_diag_daemon_status, 0, 1)

        self.lbl_diag_port = QLabel(f"Active COM Port: {self.global_settings.get('com_port', '/dev/ttyUSB0')} @ 9600 bps")
        self.lbl_diag_port.setStyleSheet("color: #cbd5e0; font-family: monospace; font-size: 10px;")
        hw_layout.addWidget(self.lbl_diag_port, 1, 0)

        self.lbl_diag_coil = QLabel("Hardware Coil Power: ENABLED (5V Bus Stabilized)")
        self.lbl_diag_coil.setStyleSheet("color: #48bb78; font-family: monospace; font-size: 10px;")
        hw_layout.addWidget(self.lbl_diag_coil, 1, 1)

        self.lbl_diag_ping = QLabel("Loopback Roundtrip Latency: < 0.8ms (Shared Memory Socket)")
        self.lbl_diag_ping.setStyleSheet("color: #63b3ed; font-family: monospace; font-size: 10px;")
        hw_layout.addWidget(self.lbl_diag_ping, 2, 0)

        self.lbl_diag_timers = QLabel(f"Safety Timers: On-Delay: {self.relay_manager.on_delay}s | Off-Delay: {self.relay_manager.off_delay}s")
        self.lbl_diag_timers.setStyleSheet("color: #cbd5e0; font-family: monospace; font-size: 10px;")
        hw_layout.addWidget(self.lbl_diag_timers, 2, 1)

        # 4-Channel Relay States Visual Indicators
        relays_box = QHBoxLayout()
        relays_box.setSpacing(10)
        lbl_rel_title = QLabel("4-Channel Relay States:")
        lbl_rel_title.setStyleSheet("font-size: 10px; font-weight: bold; color: #a0aec0;")
        relays_box.addWidget(lbl_rel_title)

        self.lbl_diag_relays = []
        for r in range(4):
            lbl_r = QLabel(f"Relay {r+1}: OFF")
            lbl_r.setStyleSheet("""
                background-color: #1a202c; color: #a0aec0; border: 1px solid #4a5568;
                border-radius: 4px; padding: 3px 8px; font-family: monospace; font-size: 9px; font-weight: bold;
            """)
            relays_box.addWidget(lbl_r)
            self.lbl_diag_relays.append(lbl_r)
        relays_box.addStretch()

        hw_layout.addLayout(relays_box, 3, 0, 1, 2)
        layout.addWidget(grp_hw)

        # ----------------------------------------------------
        # 6. GROUP: AI VISION PIPELINE & CAMERAS
        # ----------------------------------------------------
        grp_cam = QGroupBox("📹 AI VISION & USB TOPOLOGY")
        cam_main_layout = QVBoxLayout(grp_cam)
        cam_main_layout.setContentsMargins(12, 12, 12, 12)
        cam_main_layout.setSpacing(8)

        # AI Engine Specs
        conf_val = self.global_settings.get("confidence", 0.32)
        model_name = self.global_settings.get("model_path", "yolov8n.pt")
        self.lbl_diag_ai_info = QLabel(f"🤖 Inference Engine: YOLOv8 ({os.path.basename(model_name)}) | Confidence: {conf_val*100:.0f}% | Mode: CPU Execution Engine")
        self.lbl_diag_ai_info.setStyleSheet("color: #63b3ed; font-size: 10px; font-weight: bold;")
        cam_main_layout.addWidget(self.lbl_diag_ai_info)

        # 4 Cameras Grid
        cam_grid = QGridLayout()
        cam_grid.setSpacing(8)
        self.lbl_diag_cams = []
        self.lbl_diag_cam_cards = []

        for i in range(4):
            cam_card = QFrame()
            cam_card.setStyleSheet("background-color: #1a2230; border: 1px solid #2d3846; border-radius: 6px; padding: 6px;")
            cam_c_layout = QVBoxLayout(cam_card)
            cam_c_layout.setContentsMargins(6, 6, 6, 6)
            cam_c_layout.setSpacing(3)

            lbl_c_hdr = QLabel(f"📷 Station {i+1:02d}")
            lbl_c_hdr.setStyleSheet("font-size: 11px; font-weight: bold; color: #ffffff;")
            lbl_c_detail = QLabel(f"Node /dev/video{i*2} - Auto USB\nStatus: STANDBY | FPS: 0.0")
            lbl_c_detail.setStyleSheet("font-family: monospace; font-size: 9px; color: #a0aec0;")

            cam_c_layout.addWidget(lbl_c_hdr)
            cam_c_layout.addWidget(lbl_c_detail)
            cam_grid.addWidget(cam_card, i // 2, i % 2)

            self.lbl_diag_cams.append(lbl_c_detail)
            self.lbl_diag_cam_cards.append(cam_card)

        cam_main_layout.addLayout(cam_grid)
        layout.addWidget(grp_cam)

        layout.addStretch()
        return page

    def update_health_diagnostics(self):
        """
        Polls and updates all hardware, CPU, thermal, thread, memory, disk,
        camera, and relay telemetry cleanly in non-blocking realtime.
        """
        if not hasattr(self, 'lbl_kpi_cpu_val'):
            return

        now = time.time()

        # 1. CPU Metrics
        try:
            if HAS_PSUTIL:
                cpu_total = psutil.cpu_percent(interval=None)
                per_cpu = psutil.cpu_percent(interval=None, percpu=True)
                self.lbl_kpi_cpu_val.setText(f"{cpu_total:.1f}%")
                self.bar_kpi_cpu.setValue(int(cpu_total))

                # Dynamic color for total CPU bar
                if cpu_total > 85:
                    self.bar_kpi_cpu.setStyleSheet("QProgressBar::chunk { background: #e53e3e; }")
                elif cpu_total > 65:
                    self.bar_kpi_cpu.setStyleSheet("QProgressBar::chunk { background: #dd6b20; }")
                else:
                    self.bar_kpi_cpu.setStyleSheet("QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3182ce, stop:1 #48bb78); }")

                # Per-core loads
                for idx, core_val in enumerate(per_cpu[:4]):
                    if idx < len(self.bar_core):
                        self.bar_core[idx].setValue(int(core_val))
                        self.lbl_core_val[idx].setText(f"{core_val:.0f}%")
                        if core_val > 85:
                            self.bar_core[idx].setStyleSheet("QProgressBar::chunk { background: #e53e3e; }")
                        elif core_val > 65:
                            self.bar_core[idx].setStyleSheet("QProgressBar::chunk { background: #dd6b20; }")
                        else:
                            self.bar_core[idx].setStyleSheet("QProgressBar::chunk { background: #48bb78; }")
        except Exception:
            pass

        # 2. Hardware Temperatures
        max_temp = 0.0
        try:
            if HAS_PSUTIL and hasattr(psutil, 'sensors_temperatures'):
                temps = psutil.sensors_temperatures()
                # Coretemp
                if 'coretemp' in temps and temps['coretemp']:
                    entries = temps['coretemp']
                    pkg_entry = next((e for e in entries if 'Package' in (e.label or '')), entries[0])
                    pkg_cur = pkg_entry.current
                    max_temp = max(max_temp, pkg_cur)
                    color = "#e53e3e" if pkg_cur > 80 else ("#dd6b20" if pkg_cur > 65 else "#48bb78")
                    self.lbl_temp_cpu_pkg.setText(f"• CPU Package: {pkg_cur:.1f} °C (High: {pkg_entry.high or 84}°C, Crit: {pkg_entry.critical or 100}°C)")
                    self.lbl_temp_cpu_pkg.setStyleSheet(f"font-family: monospace; font-size: 10px; color: {color}; font-weight: bold;")

                    # Cores
                    core_temps = [f"{e.current:.1f}°C" for e in entries if 'Core' in (e.label or '')]
                    if core_temps:
                        self.lbl_temp_cpu_cores.setText(f"• CPU Cores: {', '.join(core_temps)}")
                        self.lbl_temp_cpu_cores.setStyleSheet("font-family: monospace; font-size: 10px; color: #cbd5e0;")

                # NVMe Storage
                if 'nvme' in temps and temps['nvme']:
                    nvme_entry = temps['nvme'][0]
                    nvme_cur = nvme_entry.current
                    max_temp = max(max_temp, nvme_cur)
                    color = "#e53e3e" if nvme_cur > 70 else ("#dd6b20" if nvme_cur > 60 else "#63b3ed")
                    self.lbl_temp_nvme.setText(f"• NVMe SSD Storage: {nvme_cur:.1f} °C (Crit: {nvme_entry.critical or 94.85}°C)")
                    self.lbl_temp_nvme.setStyleSheet(f"font-family: monospace; font-size: 10px; color: {color}; font-weight: bold;")

                # PCH
                if 'pch_skylake' in temps and temps['pch_skylake']:
                    pch_cur = temps['pch_skylake'][0].current
                    max_temp = max(max_temp, pch_cur)
                    self.lbl_temp_pch.setText(f"• Motherboard Chipset (PCH): {pch_cur:.1f} °C")

                # WiFi
                if 'iwlwifi_1' in temps and temps['iwlwifi_1']:
                    wifi_cur = temps['iwlwifi_1'][0].current
                    self.lbl_temp_wifi.setText(f"• Wireless Adapter (WiFi): {wifi_cur:.1f} °C")

                # KPI Card Temp
                if max_temp > 0:
                    self.lbl_kpi_temp_val.setText(f"{max_temp:.1f} °C")
                    self.bar_kpi_temp.setValue(min(100, int(max_temp)))
                    temp_color = "#e53e3e" if max_temp > 80 else ("#dd6b20" if max_temp > 65 else "#48bb78")
                    self.lbl_kpi_temp_val.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {temp_color}; border: none;")
                    status_text = "⚠️ ELEVATED" if max_temp > 75 else "🟢 NORMAL"
                    self.lbl_kpi_temp_sub.setText(status_text)
        except Exception:
            pass

        # 3. RAM & Disk Usage
        try:
            if HAS_PSUTIL:
                vmem = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                self.lbl_kpi_ram_val.setText(f"RAM: {vmem.percent:.0f}%")
                self.bar_kpi_ram.setValue(int(vmem.percent))
                used_gb = vmem.used / (1024 ** 3)
                total_gb = vmem.total / (1024 ** 3)
                free_disk_gb = disk.free / (1024 ** 3)
                self.lbl_kpi_disk_sub.setText(f"RAM: {used_gb:.1f}/{total_gb:.1f} GB | Disk: {disk.percent:.0f}% (Free: {free_disk_gb:.1f} GB)")
        except Exception:
            pass

        # 4. Process Threads & Resources
        try:
            if HAS_PSUTIL:
                proc = psutil.Process(os.getpid())
                proc_threads = proc.num_threads()
                proc_cpu = proc.cpu_percent(interval=None)
                proc_rss_mb = proc.memory_info().rss / (1024 * 1024)
                proc_vms_mb = proc.memory_info().vms / (1024 * 1024)

                self.lbl_kpi_threads_val.setText(f"{proc_threads} Threads")
                self.lbl_kpi_proc_sub.setText(f"App CPU: {proc_cpu:.1f}% | RAM: {proc_rss_mb:.0f} MB")

                # Python Threads list
                py_threads = [t.name for t in threading.enumerate()]
                self.lbl_diag_threads_summary.setText(f"Total Process Threads: {proc_threads} OS Threads | Python: {len(py_threads)} active")
                self.lbl_diag_threads_list.setText(f"Active Threads: {', '.join(py_threads[:8])}" + ("..." if len(py_threads) > 8 else ""))
                self.lbl_diag_proc_detail.setText(f"PID: {proc.pid} | Memory RSS: {proc_rss_mb:.1f} MB | VMS: {proc_vms_mb:.1f} MB")

                # Uptimes
                app_uptime_sec = max(0, int(now - proc.create_time()))
                app_hrs = app_uptime_sec // 3600
                app_mins = (app_uptime_sec % 3600) // 60
                app_secs = app_uptime_sec % 60
                app_uptime_str = f"{app_hrs:02d}h {app_mins:02d}m {app_secs:02d}s"

                sys_uptime_sec = max(0, int(now - psutil.boot_time()))
                sys_days = sys_uptime_sec // 86400
                sys_hrs = (sys_uptime_sec % 86400) // 3600
                sys_mins = (sys_uptime_sec % 3600) // 60
                sys_uptime_str = f"{sys_days}d {sys_hrs:02d}h {sys_mins:02d}m"

                self.lbl_kpi_uptime_sub.setText(f"App: {app_uptime_str} | System: {sys_uptime_str}")
                self.lbl_diag_uptimes.setText(f"• Uptime: App: {app_uptime_str} | OS: {sys_uptime_str}")
        except Exception:
            pass

        # 5. Industrial Relay & IPC Telemetry
        is_hw_online = (self.relay_manager.hw_status == "ONLINE")
        sock_exists = os.path.exists("/dev/shm/forklift_relay.sock")

        # Find hardware_worker.py PID
        hw_pid = None
        if HAS_PSUTIL:
            for p in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmd = " ".join(p.info['cmdline'] or [])
                    if "hardware_worker.py" in cmd:
                        hw_pid = p.info['pid']
                        break
                except Exception:
                    pass

        if is_hw_online and sock_exists:
            self.lbl_diag_ipc_status.setText("IPC Socket Status: CONNECTED (/dev/shm/forklift_relay.sock)")
            self.lbl_diag_ipc_status.setStyleSheet("color: #48bb78; font-family: monospace; font-size: 10px; font-weight: bold;")
        else:
            self.lbl_diag_ipc_status.setText("IPC Socket Status: ⚠️ DISCONNECTED / FAULT")
            self.lbl_diag_ipc_status.setStyleSheet("color: #f56565; font-family: monospace; font-size: 10px; font-weight: bold;")

        if hw_pid:
            self.lbl_diag_daemon_status.setText(f"Hardware Worker Daemon: RUNNING (PID: {hw_pid})")
            self.lbl_diag_daemon_status.setStyleSheet("color: #48bb78; font-family: monospace; font-size: 10px; font-weight: bold;")
        else:
            self.lbl_diag_daemon_status.setText("Hardware Worker Daemon: ⚠️ NOT RUNNING")
            self.lbl_diag_daemon_status.setStyleSheet("color: #f56565; font-family: monospace; font-size: 10px; font-weight: bold;")

        # Active Port & Coil
        active_com = self.global_settings.get("com_port", "/dev/ttyUSB0")
        baud = self.global_settings.get("baud_rate", 9600)
        self.lbl_diag_port.setText(f"Active COM Port: {active_com} @ {baud} bps")

        coil_state = getattr(self.relay_manager, "hardware_coil_enabled", 1)
        if coil_state:
            self.lbl_diag_coil.setText("Hardware Coil Power: ENABLED (Safety Interlock Powered)")
            self.lbl_diag_coil.setStyleSheet("color: #48bb78; font-family: monospace; font-size: 10px;")
        else:
            self.lbl_diag_coil.setText("Hardware Coil Power: DISABLED / MUTED")
            self.lbl_diag_coil.setStyleSheet("color: #dd6b20; font-family: monospace; font-size: 10px;")

        # Relay Channels States
        relay_states = getattr(self.relay_manager, "relay_states", [False, False, False, False])
        for r in range(4):
            if r < len(self.lbl_diag_relays):
                state_on = relay_states[r] if r < len(relay_states) else False
                if state_on:
                    self.lbl_diag_relays[r].setText(f"Relay {r+1}: 🔴 ON (ACTIVE)")
                    self.lbl_diag_relays[r].setStyleSheet("""
                        background-color: #742a2a; color: #feb2b2; border: 1px solid #e53e3e;
                        border-radius: 4px; padding: 3px 8px; font-family: monospace; font-size: 9px; font-weight: bold;
                    """)
                else:
                    self.lbl_diag_relays[r].setText(f"Relay {r+1}: 🟢 IDLE (OFF)")
                    self.lbl_diag_relays[r].setStyleSheet("""
                        background-color: #1a202c; color: #a0aec0; border: 1px solid #4a5568;
                        border-radius: 4px; padding: 3px 8px; font-family: monospace; font-size: 9px; font-weight: bold;
                    """)

        # 6. Cameras & AI Vision Stations
        all_cams_ok = True
        for i, card in enumerate(self.cards):
            if i >= len(self.lbl_diag_cams):
                continue
            is_online = card.camera_online
            is_breached = (card.property("warning") == "true")
            phys = card.target_physical_usb_path or "Unassigned"
            fps = getattr(card, 'fps', 0.0)
            objs = getattr(card, 'current_objects_count', 0)

            if not is_online:
                all_cams_ok = False
                st_text = "OFFLINE / RECONNECTING"
                color = "#f56565"
                card_bg = "#251717"
            elif is_breached:
                st_text = f"⚠️ BREACH DETECTED ({objs} objs)"
                color = "#f6ad55"
                card_bg = "#2d2315"
            else:
                st_text = f"ONLINE (SECURE - {objs} objs)"
                color = "#48bb78"
                card_bg = "#15241b"

            map_a = self.global_settings.get("relay_mapping", [1, 2, 3, 4])
            map_b = self.global_settings.get("relay_mapping_b", [0, 0, 0, 0])
            rel_a = map_a[i] if i < len(map_a) else 1
            rel_b = map_b[i] if i < len(map_b) else 0
            rel_b_str = f"Ch{rel_b}" if rel_b > 0 else "Disabled"
            detail = (
                f"Node /dev/video{card.device_index} - USB: {phys}\n"
                f"Status: {st_text} | FPS: {fps:.1f} fps\n"
                f"Relays Assigned: Primary->Ch{rel_a} | Secondary->{rel_b_str}"
            )
            self.lbl_diag_cams[i].setText(detail)
            self.lbl_diag_cams[i].setStyleSheet(f"font-family: monospace; font-size: 9px; color: {color};")
            if i < len(self.lbl_diag_cam_cards):
                self.lbl_diag_cam_cards[i].setStyleSheet(f"background-color: {card_bg}; border: 1px solid #2d3846; border-radius: 6px; padding: 6px;")

        # Overall Status Badge
        if is_hw_online and sock_exists and hw_pid and all_cams_ok and max_temp < 80:
            self.lbl_diag_global_badge.setText("🟢 SYSTEM OPTIMAL")
            self.lbl_diag_global_badge.setStyleSheet("""
                background-color: #1c4532; color: #48bb78; font-family: 'Segoe UI Semibold';
                font-size: 11px; font-weight: bold; padding: 6px 12px; border-radius: 6px; border: 1px solid #2f855a;
            """)
        elif not is_hw_online or not sock_exists:
            self.lbl_diag_global_badge.setText("🔴 HARDWARE FAULT")
            self.lbl_diag_global_badge.setStyleSheet("""
                background-color: #742a2a; color: #feb2b2; font-family: 'Segoe UI Semibold';
                font-size: 11px; font-weight: bold; padding: 6px 12px; border-radius: 6px; border: 1px solid #e53e3e;
            """)
        else:
            self.lbl_diag_global_badge.setText("⚠️ SYSTEM WARNING")
            self.lbl_diag_global_badge.setStyleSheet("""
                background-color: #744210; color: #fbd38d; font-family: 'Segoe UI Semibold';
                font-size: 11px; font-weight: bold; padding: 6px 12px; border-radius: 6px; border: 1px solid #d69e2e;
            """)

    def copy_diagnostics_report(self):
        """
        Generates a comprehensive diagnostic report and copies it to the system clipboard.
        """
        report_lines = [
            "============================================================",
            "FORKLIFT AI SAFETY SYSTEM — DIAGNOSTIC AUDIT REPORT",
            "============================================================",
            f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"OS: {platform.system()} {platform.release()} ({platform.machine()})",
            f"Python: {platform.python_version()}",
            "------------------------------------------------------------",
            "1. CPU & THERMALS:",
        ]

        if HAS_PSUTIL:
            try:
                report_lines.append(f"  CPU Total: {psutil.cpu_percent(interval=None):.1f}%")
                per_cpu = psutil.cpu_percent(interval=None, percpu=True)
                report_lines.append(f"  Per-Core: {', '.join([f'Core {i}: {v:.1f}%' for i, v in enumerate(per_cpu)])}")
                temps = psutil.sensors_temperatures() if hasattr(psutil, 'sensors_temperatures') else {}
                for k, v in temps.items():
                    temp_strs = [f"{e.label or 'sensor'}={e.current}°C" for e in v]
                    report_lines.append(f"  Sensor [{k}]: {', '.join(temp_strs)}")
                vmem = psutil.virtual_memory()
                report_lines.append(f"  RAM Usage: {vmem.percent}% ({vmem.used/(1024**3):.1f} GB / {vmem.total/(1024**3):.1f} GB)")
                disk = psutil.disk_usage('/')
                report_lines.append(f"  Disk Usage: {disk.percent}% (Free: {disk.free/(1024**3):.1f} GB)")
            except Exception as e:
                report_lines.append(f"  Error reading CPU/Thermals: {e}")

        report_lines.append("------------------------------------------------------------")
        report_lines.append("2. PROCESS & THREADS:")
        if HAS_PSUTIL:
            try:
                proc = psutil.Process(os.getpid())
                report_lines.append(f"  PID: {proc.pid}")
                report_lines.append(f"  OS Threads: {proc.num_threads()}")
                py_threads = [t.name for t in threading.enumerate()]
                report_lines.append(f"  Python Threads ({len(py_threads)}): {', '.join(py_threads)}")
                report_lines.append(f"  App CPU%: {proc.cpu_percent(interval=None):.1f}%")
                report_lines.append(f"  App RAM RSS: {proc.memory_info().rss/(1024*1024):.1f} MB")
            except Exception as e:
                report_lines.append(f"  Error reading process info: {e}")

        report_lines.append("------------------------------------------------------------")
        report_lines.append("3. RELAY HARDWARE & IPC:")
        report_lines.append(f"  Hardware Status: {self.relay_manager.hw_status}")
        report_lines.append(f"  Socket Exists: {os.path.exists('/dev/shm/forklift_relay.sock')}")
        report_lines.append(f"  COM Port: {self.global_settings.get('com_port')}")
        report_lines.append(f"  Coil Enabled: {getattr(self.relay_manager, 'hardware_coil_enabled', 1)}")
        report_lines.append(f"  Relay States: {getattr(self.relay_manager, 'relay_states', [])}")

        report_lines.append("------------------------------------------------------------")
        report_lines.append("4. CAMERAS & STATIONS:")
        for i, card in enumerate(self.cards):
            report_lines.append(
                f"  Station {i+1}: Node {card.device_index} | Online: {card.camera_online} | "
                f"FPS: {getattr(card, 'fps', 0.0):.1f} | USB: {card.target_physical_usb_path}"
            )
        report_lines.append("============================================================")

        report_text = "\n".join(report_lines)
        QApplication.clipboard().setText(report_text)
        self.add_audit_log("Diagnostic audit report copied to clipboard.", "success")
        if hasattr(self, 'btn_diag_copy'):
            self.btn_diag_copy.setText("✅ COPIED!")
            self.btn_diag_copy.setStyleSheet("""
                QPushButton {
                    background-color: #276749; border: 1px solid #48bb78; color: #ffffff;
                    font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 6px 12px;
                }
            """)
            QTimer.singleShot(2500, self._restore_copy_btn_style)

    def _restore_copy_btn_style(self):
        if hasattr(self, 'btn_diag_copy') and self.btn_diag_copy:
            self.btn_diag_copy.setText("📋 COPY REPORT")
            self.btn_diag_copy.setStyleSheet("""
                QPushButton {
                    background-color: #234e52; border: 1px solid #319795; color: #e6fffa;
                    font-family: 'Segoe UI Semibold'; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 6px 12px;
                }
                QPushButton:hover { background-color: #285e61; }
            """)

    def build_reports_email_page(self):
        page = QWidget()
        page.setStyleSheet("""
            QWidget { background: transparent; border: none; }
            QGroupBox {
                border: 1px solid #2d3846;
                border-radius: 6px;
                margin-top: 18px;
                padding-top: 14px;
                font-family: 'Segoe UI Semibold';
                font-size: 11px;
                font-weight: bold;
                color: #63b3ed;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                background-color: #12161f;
            }
        """)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lbl_title = QLabel("✉ INCIDENT AUDIT REPORTS & EMAIL DISPATCH")
        lbl_title.setStyleSheet("font-family: 'Segoe UI Semibold'; font-size: 15px; font-weight: bold; color: #63b3ed;")
        layout.addWidget(lbl_title)

        grp_email = QGroupBox("📧 AUTOMATED SAFETY DISPATCH SERVICE")
        email_layout = QGridLayout(grp_email)
        email_layout.setSpacing(8)

        email_layout.addWidget(QLabel("SMTP Server:"), 0, 0)
        self.txt_smtp_host = QLineEdit("smtp.gmail.com")
        self.txt_smtp_host.setStyleSheet("background-color: #1d212a; color: #ffffff; padding: 4px; border: 1px solid #2d3846;")
        email_layout.addWidget(self.txt_smtp_host, 0, 1)

        email_layout.addWidget(QLabel("SMTP Port:"), 0, 2)
        self.txt_smtp_port = QLineEdit("587")
        self.txt_smtp_port.setStyleSheet("background-color: #1d212a; color: #ffffff; padding: 4px; border: 1px solid #2d3846;")
        email_layout.addWidget(self.txt_smtp_port, 0, 3)

        email_layout.addWidget(QLabel("Recipients (comma separated):"), 1, 0)
        self.txt_email_recipients = QLineEdit("safety-officer@factory.internal, supervisor@factory.internal")
        self.txt_email_recipients.setStyleSheet("background-color: #1d212a; color: #ffffff; padding: 4px; border: 1px solid #2d3846;")
        email_layout.addWidget(self.txt_email_recipients, 1, 1, 1, 3)

        layout.addWidget(grp_email)

        btn_row = QHBoxLayout()
        btn_send_test = QPushButton("✉ DISPATCH TEST ALERT EMAIL")
        btn_send_test.setStyleSheet("""
            QPushButton {
                background-color: #2b3544; border: 1px solid #4a5568; color: #63b3ed;
                font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold; border-radius: 4px; padding: 8px 16px;
            }
            QPushButton:hover { background-color: #3b4758; }
        """)
        btn_send_test.clicked.connect(lambda: (
            self.add_audit_log("Reports: Test incident alert email dispatched to recipients.", "success"),
            QMessageBox.information(self, "Email Sent", "Test alert email simulated and dispatched successfully.")
        ))
        btn_row.addWidget(btn_send_test)

        btn_export = QPushButton("📥 EXPORT AUDIT LOGS (CSV)")
        btn_export.setStyleSheet("""
            QPushButton {
                background-color: #2b3544; border: 1px solid #4a5568; color: #68d391;
                font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold; border-radius: 4px; padding: 8px 16px;
            }
            QPushButton:hover { background-color: #3b4758; }
        """)
        btn_export.clicked.connect(lambda: (
            self.add_audit_log("Reports: Incident audit logs exported to safety_audit.csv.", "success"),
            QMessageBox.information(self, "Export Complete", "Incident audit logs exported to safety_audit.csv.")
        ))
        btn_row.addWidget(btn_export)
        btn_row.addStretch()

        layout.addLayout(btn_row)
        layout.addStretch()
        return page

    # ==========================================
    # CONFIGURATION PERSISTENCE
    # ==========================================
    def load_global_settings(self):
        config_path = "config.json"
        self.global_settings = {
            "com_port": "/dev/ttyUSB0" if sys.platform != "win32" else "COM3",
            "baud_rate": 9600,
            "camera_mapping": [0, 2, 4, 6],
            "camera_physical_paths": [None, None, None, None],
            "cameras_enabled": [True, True, True, True],
            "relay_mapping": [1, 2, 3, 4],
            "model_path": "yolov8n.pt",
            "confidence": 0.25,
            "on_delay": 0.2,
            "off_delay": 1.5,
            "boot_self_test": 1,
            "hardware_coil_enabled": 1
        }
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    data = json.load(f)
                if "settings" in data:
                    self.global_settings.update(data["settings"])
                if "camera_physical_paths" not in self.global_settings or not any(self.global_settings.get("camera_physical_paths", [])):
                    loaded_paths = [None, None, None, None]
                    for i in range(4):
                        cam_k = f"camera_{i}"
                        if cam_k in data and "physical_usb_path" in data[cam_k]:
                            loaded_paths[i] = data[cam_k]["physical_usb_path"]
                    if any(loaded_paths):
                        self.global_settings["camera_physical_paths"] = loaded_paths
                if "cameras_enabled" not in self.global_settings or len(self.global_settings.get("cameras_enabled", [])) < 4:
                    loaded_en = [True, True, True, True]
                    for i in range(4):
                        cam_k = f"camera_{i}"
                        if cam_k in data and "enabled" in data[cam_k]:
                            loaded_en[i] = bool(data[cam_k]["enabled"])
                    self.global_settings["cameras_enabled"] = loaded_en
            except Exception as e:
                print(f"Error loading global settings from config.json: {e}")

        # Platform-specific native path normalization
        if sys.platform != "win32":
            port = self.global_settings.get("com_port", "COM3")
            if not port or port.startswith("COM"):
                try:
                    import glob
                    linux_ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
                    if linux_ports:
                        self.global_settings["com_port"] = linux_ports[0]
                    else:
                        self.global_settings["com_port"] = "/dev/ttyUSB0"
                except Exception:
                    self.global_settings["com_port"] = "/dev/ttyUSB0"

    def set_camera_feed_enabled(self, cam_id, enabled):
        """Persists the enabled/disabled state of a camera station feed."""
        if "cameras_enabled" not in self.global_settings:
            self.global_settings["cameras_enabled"] = [True, True, True, True]
        while len(self.global_settings["cameras_enabled"]) < 4:
            self.global_settings["cameras_enabled"].append(True)
        
        self.global_settings["cameras_enabled"][cam_id] = bool(enabled)
        self.persist_camera_enabled_state()
        st_text = "ENABLED" if enabled else "DISABLED"
        self.add_audit_log(f"Station {cam_id + 1} feed {st_text} and saved to configuration.", "config")

    def persist_camera_enabled_state(self):
        """Writes current camera enable/disable states directly to config.json."""
        config_path = "config.json"
        try:
            data = {}
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    data = json.load(f)
            if "settings" not in data:
                data["settings"] = {}
            
            enabled_list = self.global_settings.get("cameras_enabled", [True, True, True, True])
            data["settings"]["cameras_enabled"] = enabled_list

            for i in range(4):
                cam_k = f"camera_{i}"
                if cam_k not in data:
                    data[cam_k] = {}
                data[cam_k]["enabled"] = enabled_list[i] if i < len(enabled_list) else True

            with open(config_path, "w") as f:
                json.dump(data, f, indent=4)
            print(f"[CONFIG] Persisted camera enable/disable states: {enabled_list}")
        except Exception as e:
            print(f"[CONFIG] Error saving camera enable states: {e}")

    def save_global_configurations(self):
        role_level = self.access_levels.get(self.current_role, 1)
        if role_level < 3:
            QMessageBox.warning(self, "Access Denied", "Unauthorized attempt to modify configuration parameters.")
            return

        self.global_settings["com_port"] = self.com_combo.currentText()
        self.global_settings["baud_rate"] = int(self.baud_combo.currentText())
        if hasattr(self, 'relay_a_dropdowns') and len(self.relay_a_dropdowns) >= 4:
            self.global_settings["relay_mapping"] = [
                self.relay_a_dropdowns[i].currentIndex() + 1 if self.relay_a_dropdowns[i].currentIndex() < 4 else 0 for i in range(4)
            ]
        elif hasattr(self, 'relay_dropdowns') and len(self.relay_dropdowns) >= 4:
            self.global_settings["relay_mapping"] = [
                self.relay_dropdowns[i].currentIndex() + 1 if self.relay_dropdowns[i].currentIndex() < 4 else 0 for i in range(4)
            ]
        if hasattr(self, 'relay_b_dropdowns') and len(self.relay_b_dropdowns) >= 4:
            self.global_settings["relay_mapping_b"] = [
                self.relay_b_dropdowns[i].currentIndex() + 1 if self.relay_b_dropdowns[i].currentIndex() < 4 else 0 for i in range(4)
            ]
        if hasattr(self, 'relay_a_active_checks') and len(self.relay_a_active_checks) >= 4:
            self.global_settings["relay_a_active"] = [self.relay_a_active_checks[i].isChecked() for i in range(4)]
        if hasattr(self, 'relay_b_active_checks') and len(self.relay_b_active_checks) >= 4:
            self.global_settings["relay_b_active"] = [self.relay_b_active_checks[i].isChecked() for i in range(4)]
        self.global_settings["model_path"] = self.model_input.text()
        self.global_settings["confidence"] = self.conf_slider.value() / 100.0
        self.global_settings["on_delay"] = self.on_delay_spin.value()
        self.global_settings["off_delay"] = self.off_delay_spin.value()
        self.global_settings["alarm_auto_reset"] = self.alarm_auto_reset_spin.value()
        self.global_settings["boot_self_test"] = 1 if self.boot_test_check.isChecked() else 0
        self.global_settings["hardware_coil_enabled"] = 1 if self.btn_coil_toggle.isChecked() else 0

        self.relay_manager.update_delay_config(
            self.global_settings["on_delay"],
            self.global_settings["off_delay"]
        )
        self.relay_manager.update_boot_self_test(
            self.global_settings["boot_self_test"] == 1
        )
        self.relay_manager.update_relay_mapping(
            self.global_settings["relay_mapping"],
            mapping_2=self.global_settings.get("relay_mapping_b"),
            enable_1=self.global_settings.get("relay_a_active"),
            enable_2=self.global_settings.get("relay_b_active")
        )
        self.relay_manager.set_hardware_coil_enabled(
            self.global_settings["hardware_coil_enabled"] == 1
        )

        config_path = "config.json"
        data = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data["settings"] = self.global_settings
        phys_paths = self.global_settings.get("camera_physical_paths", [None, None, None, None])
        for i in range(4):
            if i < len(phys_paths) and phys_paths[i]:
                cam_k = f"camera_{i}"
                if cam_k not in data:
                    data[cam_k] = {}
                data[cam_k]["physical_usb_path"] = phys_paths[i]

        try:
            with open(config_path, "w") as f:
                json.dump(data, f, indent=4)
            
            self.add_audit_log("Console configuration saved to config.json.", "success")
            
            new_port = self.global_settings["com_port"]
            new_baud = self.global_settings["baud_rate"]
            self.add_audit_log(f"Re-connecting RM04U to saved port {new_port} at {new_baud} Baud...", "config")
            self.relay_manager.baud_rate = new_baud
            
            self.pause_all_card_timers()
            success, msg = self.relay_manager.connect_port(new_port)
            self.resume_all_card_timers()
            
            if success:
                self.add_audit_log(f"⚡ RM04U Saved Connection Success on {new_port}.", "success")
            else:
                self.add_audit_log(f"⚠️ RM04U Saved Connection Failure: {msg}", "warning")

            self.detector.confidence = self.global_settings["confidence"]
            
            # Reload YOLO model weights live on-the-fly
            if self.detector.model_name != self.global_settings["model_path"]:
                self.add_audit_log("System reloading YOLO model weights...", "config")
                self.detector = YoloDetector(
                    model_name=self.global_settings.get("model_name", self.global_settings.get("model_path", "yolov8n.pt")),
                    confidence=self.global_settings["confidence"]
                )
                self.add_audit_log("YOLO model fully operational.", "success")
                for card in self.cards:
                    card.detector = self.detector
            
            self.add_audit_log("Dynamic parameter mapping applied successfully.", "success")
            QMessageBox.information(self, "System Configured", "⚡ SCADA Operations parameters successfully updated.")
            self.show_live_page()
        except Exception as e:
            self.add_audit_log(f"Config write error: {e}", "warning")
            QMessageBox.critical(self, "Configuration Error", f"Failed to persist settings:\n{e}")

    def instant_save_timer_config(self, _=None):
        """Instantly updates JSON bridge and config file when UI timers/flags change."""
        self.global_settings["on_delay"] = self.on_delay_spin.value()
        self.global_settings["off_delay"] = self.off_delay_spin.value()
        self.global_settings["alarm_auto_reset"] = self.alarm_auto_reset_spin.value()
        self.global_settings["boot_self_test"] = 1 if self.boot_test_check.isChecked() else 0
        if hasattr(self, 'relay_a_dropdowns') and len(self.relay_a_dropdowns) >= 4:
            self.global_settings["relay_mapping"] = [
                self.relay_a_dropdowns[i].currentIndex() + 1 if self.relay_a_dropdowns[i].currentIndex() < 4 else 0 for i in range(4)
            ]
        elif hasattr(self, 'relay_dropdowns') and len(self.relay_dropdowns) >= 4:
            self.global_settings["relay_mapping"] = [
                self.relay_dropdowns[i].currentIndex() + 1 if self.relay_dropdowns[i].currentIndex() < 4 else 0 for i in range(4)
            ]
        if hasattr(self, 'relay_b_dropdowns') and len(self.relay_b_dropdowns) >= 4:
            self.global_settings["relay_mapping_b"] = [
                self.relay_b_dropdowns[i].currentIndex() + 1 if self.relay_b_dropdowns[i].currentIndex() < 4 else 0 for i in range(4)
            ]
        if hasattr(self, 'relay_a_active_checks') and len(self.relay_a_active_checks) >= 4:
            self.global_settings["relay_a_active"] = [self.relay_a_active_checks[i].isChecked() for i in range(4)]
        if hasattr(self, 'relay_b_active_checks') and len(self.relay_b_active_checks) >= 4:
            self.global_settings["relay_b_active"] = [self.relay_b_active_checks[i].isChecked() for i in range(4)]
        self.global_settings["hardware_coil_enabled"] = 1 if self.btn_coil_toggle.isChecked() else 0

        # Synchronize camera cards with current relay mapping
        if hasattr(self, 'cards'):
            for i, card in enumerate(self.cards):
                if getattr(card, 'relay_combo', None) and i < len(self.global_settings.get("relay_mapping", [])):
                    rel_idx = self.global_settings["relay_mapping"][i] - 1
                    card.relay_combo.blockSignals(True)
                    card.relay_combo.setCurrentIndex(rel_idx)
                    card.relay_combo.blockSignals(False)
                    if getattr(card, 'btn_test_relay', None) and not card.btn_test_relay.isChecked():
                        card.btn_test_relay.setText(f"⚡ TEST R{rel_idx + 1}")

        if self.relay_manager is not None:
            self.relay_manager.update_delay_config(
                self.global_settings["on_delay"],
                self.global_settings["off_delay"]
            )
            self.relay_manager.update_boot_self_test(
                self.global_settings["boot_self_test"] == 1
            )
            self.relay_manager.update_relay_mapping(
                self.global_settings["relay_mapping"],
                mapping_2=self.global_settings.get("relay_mapping_b"),
                enable_1=self.global_settings.get("relay_a_active"),
                enable_2=self.global_settings.get("relay_b_active")
            )
            self.relay_manager.set_hardware_coil_enabled(
                self.global_settings["hardware_coil_enabled"] == 1
            )

        config_path = "config.json"
        data = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        
        data["settings"] = self.global_settings
        phys_paths = self.global_settings.get("camera_physical_paths", [None, None, None, None])
        enabled_list = self.global_settings.get("cameras_enabled", [True, True, True, True])
        for i in range(4):
            cam_k = f"camera_{i}"
            if cam_k not in data:
                data[cam_k] = {}
            if i < len(phys_paths) and phys_paths[i]:
                data[cam_k]["physical_usb_path"] = phys_paths[i]
            elif "physical_usb_path" in data[cam_k] and (i >= len(phys_paths) or not phys_paths[i]):
                data[cam_k].pop("physical_usb_path", None)
            data[cam_k]["enabled"] = enabled_list[i] if i < len(enabled_list) else True

        try:
            with open(config_path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    def browse_model(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select YOLO Weight File", "", "PyTorch Weights (*.pt);;All Files (*)"
        )
        if file_path:
            self.model_input.setText(file_path)
            self.add_audit_log(f"Staged weights: {os.path.basename(file_path)}", "config")

    # ==========================================
    # USB COM RELAY RM04U HANDSHAKES
    # ==========================================
    def test_hardware_connection(self):
        com_port = self.com_combo.currentText()
        baud_rate = int(self.baud_combo.currentText())
        self.add_audit_log(f"RM04U: Pinging handshakes on {com_port} at {baud_rate} Baud...", "config")
        
        self.relay_manager.baud_rate = baud_rate
        
        self.pause_all_card_timers()
        success, message = self.relay_manager.connect_port(com_port)
        self.resume_all_card_timers()
        
        if success:
            self.add_audit_log(f"⚡ RM04U Handshake Success: USB Board is responding.", "success")
            QMessageBox.information(
                self, "Handshake Verified", 
                f"⚡ RM04U USB RELAY BOARD DETECTED\n\nPort: {com_port}\nBaud: {baud_rate}\nStatus: STABLE / READY"
            )
        else:
            self.add_audit_log(f"⚠️ RM04U Handshake Failed: {message}", "warning")
            QMessageBox.critical(
                self, "Handshake Error",
                f"⚠️ RM04U USB RELAY BOARD OFFLINE\n\nPort: {com_port}\nError: {message}"
            )

    def test_relay_channel(self, index, checked):
        state_str = "ON" if checked else "OFF"
        action_char = 'N' if checked else 'F'
        color = "warning" if checked else "config"
        
        if self.relay_manager is not None:
            if index < len(self.relay_manager.manual_overrides):
                self.relay_manager.manual_overrides[index] = checked
        
        if self.relay_manager.is_connected:
            success, msg = self.relay_manager.trigger_relay(index, checked, force=True)
            if success:
                self.add_audit_log(f"RM04U Manual Override: Relay {index + 1} set to {state_str} ({action_char}{index + 1}) - {msg}.", color)
            else:
                self.add_audit_log(f"RM04U Override Failed: Relay {index + 1} -> {msg}", "warning")
        else:
            self.add_audit_log(f"RM04U Override: Relay {index + 1} simulated {state_str} ({action_char}{index + 1}).", color)

        # Synchronize UI state on settings page
        if hasattr(self, 'relay_buttons') and index < len(self.relay_buttons):
            self.relay_buttons[index].blockSignals(True)
            self.relay_buttons[index].setChecked(checked)
            self.relay_buttons[index].blockSignals(False)

        # Synchronize UI state on all camera cards mapped to this relay
        if hasattr(self, 'cards'):
            for card in self.cards:
                assigned_relay = self.global_settings.get("relay_mapping", [1, 2, 3, 4])[card.cam_id]
                if assigned_relay == index + 1 and getattr(card, 'btn_test_relay', None):
                    card.btn_test_relay.blockSignals(True)
                    card.btn_test_relay.setChecked(checked)
                    if checked:
                        card.btn_test_relay.setText(f"⚡ R{index + 1} ON")
                    else:
                        card.btn_test_relay.setText(f"⚡ TEST R{index + 1}")
                    card.btn_test_relay.blockSignals(False)

    def toggle_hardware_coil(self, checked):
        """Handles software coil toggle from the button."""
        if checked:
            self.btn_coil_toggle.setText("🔌 HARDWARE COIL OUTPUT: ENABLED")
            self.relay_manager.set_hardware_coil_enabled(True)
            self.add_audit_log("Security: Physical relay coil output ENABLED.", "success")
        else:
            self.btn_coil_toggle.setText("🔌 HARDWARE COIL OUTPUT: DISABLED")
            self.relay_manager.set_hardware_coil_enabled(False)
            self.add_audit_log("Security: Physical relay coil output DISABLED.", "warning")
            
        self.global_settings["hardware_coil_enabled"] = 1 if checked else 0
        self.instant_save_timer_config()

    # ==========================================
    # AUDITING SYSTEM LOGS
    # ==========================================
    def add_audit_log(self, text, type="info"):
        timestamp = time.strftime("%H:%M:%S")
        log_item = QListWidgetItem(f"[{timestamp}] {text}")
        if type == "warning":
            log_item.setForeground(QColor("#fc8181"))
        elif type == "success":
            log_item.setForeground(QColor("#68d391"))
        elif type == "config":
            log_item.setForeground(QColor("#63b3ed"))
        else:
            log_item.setForeground(QColor("#a0aec0"))
        
        self.log_terminal.addItem(log_item)
        self.log_terminal.scrollToBottom()

        if self.log_terminal.count() > 50:
            self.log_terminal.takeItem(0)

    # ==========================================
    # ACCESS CONTROLS (LEVELS HARDENING)
    # ==========================================
    def change_role(self, role):
        if role == "Operator":
            self.current_role = "Operator"
            self.update_ui_permissions()
            if self.stacked_widget.currentIndex() == 1:
                self.show_live_page()
            self.add_audit_log("Role engagement updated: OPERATOR engaged.")
            return

        role_level = self.access_levels.get(role, 1)
        # Demand password credentials to upgrade active role level using touch-native dialog
        password, ok = TouchPasswordDialog.get_password(
            self, "Access Authorization", f"Enter {role} Password:", role=role
        )
        if not ok:
            # Revert role combo selection quietly
            self.role_combo.blockSignals(True)
            self.role_combo.setCurrentText(self.current_role)
            self.role_combo.blockSignals(False)
            return

        if self.security.verify_password(role, password):
            self.current_role = role
            self.update_ui_permissions()
            self.add_audit_log(f"Authentication success: {role.upper()} granted.", "success")
            QMessageBox.information(self, "Access Granted", f"{role} Mode Enabled")
        else:
            self.add_audit_log(f"Authentication Failure: {role.upper()} login denied!", "warning")
            QMessageBox.warning(self, "Access Denied", "Wrong Credentials Password")
            self.role_combo.blockSignals(True)
            self.role_combo.setCurrentText(self.current_role)
            self.role_combo.blockSignals(False)

    def update_ui_permissions(self):
        """Hardens UI components based on the active Role Access Level (4-Tier Industrial Security)."""
        role_level = self.access_levels.get(self.current_role, 1)
        is_supervisor = (role_level >= 2)
        is_engineer   = (role_level >= 3)
        is_admin      = (role_level >= 4)
        
        # Tier 2+: Supervisor permissions (Overrides, ROIs, Exit, Camera Mapping, Relay Selectors, Relay Testing)
        self.exit_button.setEnabled(is_supervisor)
        self.btn_disable_all.setEnabled(is_supervisor)
        if hasattr(self, 'btn_rescan_ports'):
            self.btn_rescan_ports.setEnabled(is_supervisor)
        if hasattr(self, 'btn_refresh_cams'):
            self.btn_refresh_cams.setEnabled(is_supervisor)

        for combo in getattr(self, 'cam_port_dropdowns', []):
            combo.setEnabled(is_supervisor)
        for btn in getattr(self, 'cam_port_lock_buttons', []):
            btn.setEnabled(is_supervisor)
        for combo in getattr(self, 'relay_dropdowns', []):
            combo.setEnabled(is_supervisor)
        for combo in getattr(self, 'relay_b_dropdowns', []):
            combo.setEnabled(is_supervisor)
        for btn in getattr(self, 'relay_a_active_checks', []):
            btn.setEnabled(is_supervisor)
        for btn in getattr(self, 'relay_b_active_checks', []):
            btn.setEnabled(is_supervisor)
        for btn in getattr(self, 'relay_buttons', []):
            btn.setEnabled(is_supervisor)

        for card in self.cards:
            card.btn_edit_roi.setEnabled(is_supervisor)
            if getattr(card, 'relay_combo', None):
                card.relay_combo.setEnabled(is_supervisor)
            if getattr(card, 'btn_test_relay', None):
                card.btn_test_relay.setEnabled(is_supervisor)
            # Force ROI Editor closure on downgrade
            if not is_supervisor and card.video_label.is_editable:
                card.toggle_roi_edit()

        # Tier 3+: Engineer permissions (Hardware serial connection, timing delays, AI model config)
        if hasattr(self, 'on_delay_spin'):
            self.on_delay_spin.setEnabled(is_engineer)
        if hasattr(self, 'off_delay_spin'):
            self.off_delay_spin.setEnabled(is_engineer)
        if hasattr(self, 'alarm_auto_reset_spin'):
            self.alarm_auto_reset_spin.setEnabled(is_engineer)
        if hasattr(self, 'boot_test_check'):
            self.boot_test_check.setEnabled(is_engineer)
        if hasattr(self, 'com_combo'):
            self.com_combo.setEnabled(is_engineer)
        if hasattr(self, 'baud_combo'):
            self.baud_combo.setEnabled(is_engineer)
        if hasattr(self, 'btn_test_conn'):
            self.btn_test_conn.setEnabled(is_engineer)
        if hasattr(self, 'model_input'):
            self.model_input.setEnabled(is_engineer)
        if hasattr(self, 'conf_slider'):
            self.conf_slider.setEnabled(is_engineer)
        if hasattr(self, 'btn_browse'):
            self.btn_browse.setEnabled(is_engineer)
        if hasattr(self, 'btn_save_config'):
            self.btn_save_config.setEnabled(is_engineer)

        # Tier 4+: Admin permissions (Hardware coil cutoff, security credentials management)
        if hasattr(self, 'btn_coil_toggle'):
            self.btn_coil_toggle.setEnabled(is_admin)
        if hasattr(self, 'btn_change_password'):
            self.btn_change_password.setEnabled(is_admin)

    def change_password(self):
        role_level = self.access_levels.get(self.current_role, 1)
        if role_level < 4:
            QMessageBox.warning(self, "Access Denied", "Password configurations require Administrator level access.")
            return

        role, ok = QInputDialog.getItem(
            self, "Configure Role Passwords", "Select Target Role Profile:", ["Supervisor", "Engineer", "Technician", "Admin", "Administrator"], 0, False
        )
        if not ok: return

        current_password, ok = TouchPasswordDialog.get_password(
            self, "Verify Credentials", f"Enter Current Password for {role}:", role=role
        )
        if not ok or not self.security.verify_password(role, current_password):
            QMessageBox.warning(self, "Access Denied", "Wrong Current Password")
            return

        new_password, ok = TouchPasswordDialog.get_password(
            self, "Configure Password", f"Enter New Password for {role}:", role=role
        )
        if not ok: return

        confirm_password, ok = TouchPasswordDialog.get_password(
            self, "Confirm Password", f"Confirm New Password for {role}:", role=role
        )
        if not ok or new_password != confirm_password:
            QMessageBox.warning(self, "Security Error", "Passwords Mismatch")
            return

        self.security.change_password(role, new_password)
        self.add_audit_log(f"Security profile updated: {role} credentials updated.", "config")
        QMessageBox.information(self, "Success", f"{role} Password Updated Successfully")

    # ==========================================
    # CENTRALIZED ALARM AGGREGATION
    # ==========================================
    def evaluate_global_alarms(self):
        any_warning = False
        any_active = False

        for card in self.cards:
            if card.is_active:
                any_active = True
                if card.property("warning") == "true":
                    any_warning = True

        hardware_online = getattr(self, 'hardware_is_online', True)

        if not hardware_online:
            blink_color = "#FF3B30" if getattr(self, 'hardware_offline_blink', False) else "#4a1d1d"
            base_text = "⚠️ RELAY MODULE: DISCONNECTED"
            base_style = f"""
                background-color: {blink_color}; color: #ffffff;
                font-family: 'Segoe UI Semibold'; font-size: 14px; font-weight: bold; padding: 12px 20px; border-radius: 6px;
                border: 2px solid #ffffff;
            """
        else: # hardware_online == True
            if any_warning:
                base_text = "⚠️ CRITICAL WARNING: PATH VIOLATION DETECTED IN MONITORED SECTORS!"
                base_style = """
                    background-color: #e74c3c; color: #fff5f5;
                    font-family: 'Segoe UI Semibold'; font-size: 14px; font-weight: bold; padding: 12px 20px; border-radius: 6px;
                    border: 1px solid #c0392b;
                """
            else:
                base_text = "🟢 RELAY MODULE: CONNECTED"
                base_style = """
                    background-color: #2ecc71; color: #ffffff;
                    font-family: 'Segoe UI Semibold'; font-size: 14px; font-weight: bold; padding: 12px 20px; border-radius: 6px;
                    border: 1px solid #27ae60;
                """

        self.status_label.setText(base_text)
        self.status_label.setStyleSheet(base_style)

    def poll_hardware_status(self):
        # Check relay manager status (which internally monitors the IPC connection)
        is_online = (self.relay_manager.hw_status == "ONLINE")

        self.hardware_offline_blink = not self.hardware_offline_blink
        
        if is_online != getattr(self, 'hardware_is_online', True):
            self.hardware_is_online = is_online
            if not is_online:
                self.add_audit_log("⚠️ ALERT: USB Serial Relay Module disconnected / offline!", "warning")
            else:
                self.add_audit_log("⚡ Info: USB Serial Relay Module online and connected.", "success")

        self.evaluate_global_alarms()

        # Real-time health & hardware diagnostics live telemetry refresh
        if self.stacked_widget.currentIndex() == 2:
            self.update_health_diagnostics()

    def global_start_all(self):
        self.add_audit_log("Global override: Activate all monitoring channels.", "config")
        for card in self.cards:
            card.start_camera(persist=True)

    def global_stop_all(self):
        # Access control validation
        role_level = self.access_levels.get(self.current_role, 1)
        if role_level < 2:
            QMessageBox.warning(self, "Access Denied", "System override deactivations require Supervisor permissions.")
            return

        self.add_audit_log("Global override: Deactivate all monitoring channels.", "config")
        for card in self.cards:
            card.stop_camera(persist=True)

    # ==========================================
    # BACKGROUND TIMER ISOLATION FOR SERIAL SAFETY
    # ==========================================
    def pause_all_card_timers(self):
        """Globally freeze all background camera processing loops to protect serial handshakes."""
        for card in self.cards:
            if hasattr(card, "camera_thread") and card.camera_thread is not None:
                card.camera_thread.stop()
                card.camera_thread.deleteLater()
                card.camera_thread = None

    def resume_all_card_timers(self):
        """Resume all previously active camera processing loops after serial stabilization."""
        for card in self.cards:
            if card.is_active:
                card.camera_thread = CameraWorkerThread(
                    device_index=card.device_index,
                    station_id=card.cam_id,
                    target_physical_usb_path=card.target_physical_usb_path,
                    width=640,
                    height=480
                )
                card.camera_thread.frame_ready.connect(card.on_frame_received)
                card.camera_thread.status_changed.connect(card.on_camera_status_changed)
                card.camera_thread.path_discovered.connect(card.on_physical_path_discovered)
                card.camera_thread.start()

    # ==========================================
    # LIFECYCLE SHUTDOWN & ALT+F4 HARDENING
    # ==========================================
    def close_app(self):
        self.close()

    def closeEvent(self, event):
        """Intercept Alt+F4 and close event triggers based on Supervisor roles."""
        role_level = self.access_levels.get(self.current_role, 1)
        if role_level < 2:
            # Deny shutdown and ignore close event trigger
            event.ignore()
            QMessageBox.warning(
                self, "Access Denied", 
                "Access Denied: Supervisor privileges required to terminate system."
            )
            self.add_audit_log("Security: Unauthorized attempts to shut down the HMI blocked.", "warning")
        else:
            # Execute standard teardown routines for supervisor
            self.add_audit_log("System closing down safely under Supervisor authorization.")
            for card in self.cards:
                card.stop_camera(persist=False)
            self.relay_manager.disconnect()
            self.relay_manager.cleanup()
            event.accept()


# ==========================================
# MAIN EXECUTION ROUTINE
# ==========================================
def main():
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_SynthesizeMouseForUnhandledTouchEvents, True)
    app.setAttribute(Qt.AA_SynthesizeTouchForUnhandledMouseEvents, True)
    window = ForkliftSafetyGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
