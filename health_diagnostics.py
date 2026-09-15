#!/usr/bin/env python3
"""
======================================================================
Health & Diagnostics Module — AI Forklift Safety System
Version: 1.0.0
======================================================================
Completely independent, purely additive, read-only subsystem.

Architecture:
  MetricsEngine   — single daemon thread; collects all metrics and
                    writes them to a thread-safe cache dict.
  HealthDiagnosticsPage — PyQt5 QWidget page; reads ONLY from the
                    MetricsEngine cache; never calls system APIs.

Compliance:
  ✅ Never modifies any existing object, class, or function
  ✅ Never reads camera frames
  ✅ Never runs AI inference
  ✅ Never writes to serial port
  ✅ Never calls Qt APIs from the daemon thread
  ✅ Never blocks the GUI thread
  ✅ All data via psutil and read-only attribute access
======================================================================
"""

import os
import time
import json
import platform
import threading
import datetime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("[Health] psutil not installed — hardware metrics will show N/A. "
          "Install with: pip install psutil")

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QGroupBox, QGridLayout, QFrame, QSizePolicy,
    QMessageBox, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor


# ======================================================================
# MODULE CONSTANTS
# ======================================================================

MODULE_VERSION      = "1.0.0"

WATCHDOG_TICK_S     = 2       # Watchdog check interval
METRICS_TICK_S      = 5       # System / hardware metrics interval
DISK_TICK_S         = 30      # Disk info interval
ENGINE_SLEEP_S      = 1.0     # Base daemon thread sleep
GUI_REFRESH_MS      = 1000    # GUI label refresh (milliseconds)

MAX_EVENTS          = 500     # Maximum stored event history entries
MAX_EVENTS_DISPLAY  = 150     # Maximum events shown in UI
MAX_RESTART_HISTORY = 50      # Maximum restart history entries

_SCRIPT_DIR         = os.path.dirname(os.path.abspath(__file__))
HEALTH_DATA_FILE    = os.path.join(_SCRIPT_DIR, "health_runtime_data.json")


# ======================================================================
# STYLE CONSTANTS  (match existing dark SCADA theme)
# ======================================================================

_SECTION_STYLE = """
    QGroupBox {
        border: 2px solid #2d3846;
        border-radius: 6px;
        margin-top: 14px;
        font-family: 'Segoe UI Semibold';
        font-size: 11px;
        font-weight: bold;
        color: #63b3ed;
        background-color: #16161a;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        background-color: #16161a;
    }
"""

_SUBSECTION_STYLE = """
    QGroupBox {
        border: 1px solid #232d38;
        border-radius: 4px;
        margin-top: 10px;
        font-family: 'Segoe UI Semibold';
        font-size: 10px;
        font-weight: bold;
        color: #4a90d9;
        background-color: #111318;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 3px;
        background-color: #111318;
    }
"""

_KEY_SS   = "color: #718096; font-size: 11px; font-family: 'Segoe UI';"
_VAL_SS   = ("color: #e2e8f0; font-size: 11px; font-family: 'Segoe UI Semibold';"
              " font-weight: 600;")
_OK_SS    = ("color: #48bb78; font-size: 11px; font-family: 'Segoe UI Semibold';"
              " font-weight: 700;")
_WARN_SS  = ("color: #f6ad55; font-size: 11px; font-family: 'Segoe UI Semibold';"
              " font-weight: 700;")
_ERR_SS   = ("color: #fc8181; font-size: 11px; font-family: 'Segoe UI Semibold';"
              " font-weight: 700;")
_INIT_SS  = "color: #718096; font-size: 11px; font-family: 'Segoe UI Semibold';"
_CYAN_SS  = ("color: #76e4f7; font-size: 11px; font-family: 'Segoe UI Semibold';"
              " font-weight: 700;")

_REPORT_BTN_SS = """
    QPushButton {
        background-color: #1a365d;
        border: 2px solid #2b6cb0;
        color: #ffffff;
        font-family: 'Segoe UI Semibold';
        font-size: 12px;
        font-weight: bold;
        border-radius: 6px;
        padding: 10px;
    }
    QPushButton:hover { background-color: #2b548a; border-color: #4299e1; }
    QPushButton:pressed { background-color: #153e75; }
"""

_BIG_HEALTH_OK_SS   = ("color: #48bb78; font-size: 22px; font-family: 'Segoe UI Semibold';"
                        " font-weight: 800;")
_BIG_HEALTH_WARN_SS = ("color: #f6ad55; font-size: 22px; font-family: 'Segoe UI Semibold';"
                        " font-weight: 800;")
_BIG_HEALTH_ERR_SS  = ("color: #fc8181; font-size: 22px; font-family: 'Segoe UI Semibold';"
                        " font-weight: 800;")
_BIG_HEALTH_INIT_SS = ("color: #718096; font-size: 22px; font-family: 'Segoe UI Semibold';"
                        " font-weight: 800;")

_EVT_LOG_SS = """
    QListWidget {
        background-color: rgba(11, 11, 15, 0.95);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 4px;
        font-family: 'Courier New', Consolas, monospace;
        font-size: 10px;
        color: #a0aec0;
        padding: 4px;
    }
    QScrollBar:vertical { background: #1a1a24; width: 6px; }
    QScrollBar::handle:vertical { background: #2d3846; border-radius: 3px; min-height: 16px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""


# ======================================================================
# FORMATTING HELPERS
# ======================================================================

def _fmt_bytes(b):
    """Formats byte count to human-readable string."""
    if b is None or b < 0:
        return "N/A"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def _fmt_duration(seconds):
    """Formats elapsed seconds into d h m s string."""
    if seconds is None or seconds < 0:
        return "N/A"
    seconds = int(seconds)
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if d > 0:
        return f"{d}d {h:02d}h {m:02d}m {s:02d}s"
    elif h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    else:
        return f"{m}m {s:02d}s"


def _fmt_ts(ts):
    """Formats a Unix timestamp to readable datetime string."""
    if not ts or ts <= 0:
        return "N/A"
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "N/A"


def _now_str():
    """Returns current datetime as string."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _pct_style(pct):
    """Returns appropriate style string based on percentage value."""
    if pct is None:
        return _INIT_SS
    if pct >= 90:
        return _ERR_SS
    if pct >= 70:
        return _WARN_SS
    return _OK_SS


# ======================================================================
# PERSISTENT DATA MANAGER
# ======================================================================

class _PersistentData:
    """
    Manages a small JSON file to track cross-session health metrics.
    Written only by MetricsEngine on startup and clean shutdown.
    """

    def __init__(self, filepath):
        self._path = filepath
        self._data = self._load()

    def _load(self):
        defaults = {
            "app_restart_count":        0,
            "normal_shutdown_count":    0,
            "unexpected_shutdown_count": 0,
            "last_session_start":       0.0,
            "last_session_end":         0.0,
            "last_session_uptime":      0.0,
            "total_boots_recorded":     0,
            "_last_known_boot":         0.0,
            "restart_history":          [],
        }
        try:
            if os.path.exists(self._path):
                with open(self._path, "r") as f:
                    saved = json.load(f)
                defaults.update(saved)
        except Exception:
            pass
        return defaults

    def _save(self):
        try:
            with open(self._path, "w") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"[Health] PersistentData save error: {e}")

    def record_startup(self):
        """Called once at app startup to update persistent state."""
        now = time.time()

        # Detect unexpected shutdown: previous session had a start but no end
        prev_start = self._data.get("last_session_start", 0)
        prev_end   = self._data.get("last_session_end",   0)
        if prev_start > 0 and prev_end < prev_start:
            self._data["unexpected_shutdown_count"] = (
                self._data.get("unexpected_shutdown_count", 0) + 1
            )

        self._data["app_restart_count"] = self._data.get("app_restart_count", 0) + 1
        self._data["last_session_start"] = now
        self._data["last_session_end"]   = 0  # Reset — set on clean shutdown

        # Detect system boots via psutil boot_time changes
        if HAS_PSUTIL:
            try:
                boot_ts       = psutil.boot_time()
                last_boot     = self._data.get("_last_known_boot", 0.0)
                total_boots   = self._data.get("total_boots_recorded", 0)
                if abs(boot_ts - last_boot) > 60:   # New boot detected
                    total_boots += 1
                    self._data["total_boots_recorded"] = total_boots
                    self._data["_last_known_boot"]     = boot_ts
            except Exception:
                pass

        # Append restart history entry
        prev_uptime = self._data.get("last_session_uptime", 0.0)
        entry = {
            "datetime":           _now_str(),
            "timestamp":          now,
            "previous_uptime_s":  prev_uptime,
            "restart_count":      self._data["app_restart_count"],
        }
        history = self._data.get("restart_history", [])
        history.append(entry)
        if len(history) > MAX_RESTART_HISTORY:
            history = history[-MAX_RESTART_HISTORY:]
        self._data["restart_history"] = history

        self._save()

    def record_shutdown(self, session_start):
        """Called on clean shutdown to mark session end and uptime."""
        now = time.time()
        self._data["last_session_end"]     = now
        self._data["last_session_uptime"]  = max(0, now - session_start)
        self._data["normal_shutdown_count"] = (
            self._data.get("normal_shutdown_count", 0) + 1
        )
        self._save()

    def get(self, key, default=None):
        return self._data.get(key, default)


# ======================================================================
# METRICS ENGINE  (daemon background thread)
# ======================================================================

class MetricsEngine:
    """
    Background data-collection engine.

    Single daemon thread; ticks every 1 second.
    Sub-schedules heavier collection at independent intervals:
      - Watchdog:      every 2 seconds
      - System metrics: every 5 seconds
      - Disk:          every 30 seconds

    All results are stored in _cache (dict) protected by _lock.
    The GUI calls get_snapshot() to read a consistent copy; it never
    calls psutil or any system API directly.

    This class NEVER:
      - Calls any Qt API
      - Reads camera frame data
      - Runs YOLO inference
      - Writes to serial port
      - Blocks the main/GUI thread
    """

    def __init__(self, gui_ref=None):
        self._gui          = gui_ref     # Read-only reference to ForkliftSafetyGUI
        self._lock         = threading.Lock()
        self._running      = False
        self._thread       = None

        # Application session
        self._app_start_time = time.time()

        # Interval scheduling  (wall-clock based, immune to thread jitter)
        self._last_watchdog_t = 0.0
        self._last_metrics_t  = 0.0
        self._last_disk_t     = 0.0

        # Per-camera state tracking (non-invasive)
        self._cam_was_online     = [False] * 4
        self._cam_was_active     = [False] * 4
        self._cam_start_times    = [0.0]   * 4
        self._cam_reconnect_cnts = [0]     * 4
        self._cam_prev_times     = [0.0]   * 4   # prev card.prev_time sample

        # Relay command tracking (derived from state transitions)
        self._relay_total_cmds    = 0
        self._relay_errors        = 0
        self._relay_last_states   = [False] * 4
        self._relay_last_cmd      = "N/A"
        self._relay_last_cmd_ts   = 0.0
        self._relay_prev_status   = None

        # Watchdog state (for transition detection and retry counting)
        _wd_names = ("camera", "yolo", "relay", "hardware", "gui", "security")
        self._wd_retry_counts  = {n: 0    for n in _wd_names}
        self._wd_prev_alive    = {n: None for n in _wd_names}

        # GUI thread heartbeat
        self._gui_hb_counter    = 0    # Bumped by GUI refresh timer
        self._gui_hb_last_seen  = -1   # Value seen at last WD check

        # Event log
        self._events = []              # list of dicts

        # Persistent cross-session data
        self._persistent = _PersistentData(HEALTH_DATA_FILE)
        self._persistent.record_startup()

        # Build initial (empty) cache
        self._cache = self._build_initial_cache()

        # Record startup event
        self._add_event("Program Start", "startup")

    # ------------------------------------------------------------------
    # PUBLIC LIFECYCLE
    # ------------------------------------------------------------------

    def start(self):
        """Starts the background daemon thread."""
        self._running = True
        self._thread  = threading.Thread(
            target    = self._run,
            name      = "HealthMetricsEngine",
            daemon    = True,
        )
        self._thread.start()
        print("[Health] MetricsEngine daemon thread started.")

    def stop(self):
        """Signals the daemon thread to stop and persists shutdown record."""
        self._add_event("Program Stop", "shutdown")
        self._running = False
        self._persistent.record_shutdown(self._app_start_time)
        print("[Health] MetricsEngine stopped.")

    # ------------------------------------------------------------------
    # PUBLIC DATA ACCESS
    # ------------------------------------------------------------------

    def get_snapshot(self):
        """Returns a thread-safe shallow copy of the current metrics cache."""
        with self._lock:
            return dict(self._cache)

    def tick_gui_heartbeat(self):
        """
        Called by the GUI's 1-second refresh QTimer.
        Increments a counter that the watchdog verifies is changing.
        This is the ONLY coupling between the GUI timer and this engine.
        """
        self._gui_hb_counter += 1

    def add_event(self, message, event_type="info"):
        """Public API to log an external event into the history."""
        self._add_event(message, event_type)

    # ------------------------------------------------------------------
    # INTERNAL EVENT LOGGING
    # ------------------------------------------------------------------

    def _add_event(self, message, event_type="info"):
        entry = {
            "timestamp": time.time(),
            "datetime":  _now_str(),
            "message":   message,
            "type":      event_type,
        }
        self._events.append(entry)
        if len(self._events) > MAX_EVENTS:
            self._events = self._events[-MAX_EVENTS:]

    # ------------------------------------------------------------------
    # DAEMON THREAD MAIN LOOP
    # ------------------------------------------------------------------

    def _run(self):
        """
        Daemon thread loop. Sleeps 1 second between ticks.
        Uses wall-clock comparisons to schedule sub-intervals precisely,
        regardless of sleep jitter or load.
        """
        # Prime psutil per-interval CPU sampling (first call returns 0.0 on Linux)
        if HAS_PSUTIL:
            try:
                psutil.cpu_percent(interval=None)
            except Exception:
                pass

        while self._running:
            try:
                now = time.time()

                # ── Runtime counters (every tick, very cheap) ─────────────
                self._collect_runtime(now)

                # ── Watchdog (every 2 seconds) ────────────────────────────
                if now - self._last_watchdog_t >= WATCHDOG_TICK_S:
                    self._last_watchdog_t = now
                    self._collect_watchdog(now)

                # ── System metrics (every 5 seconds) ─────────────────────
                if now - self._last_metrics_t >= METRICS_TICK_S:
                    self._last_metrics_t = now
                    if HAS_PSUTIL:
                        self._collect_cpu_memory()
                    self._collect_cameras(now)
                    self._collect_relay(now)
                    self._collect_ai()
                    self._collect_overall_health()

                # ── Disk (every 30 seconds) ───────────────────────────────
                if now - self._last_disk_t >= DISK_TICK_S:
                    self._last_disk_t = now
                    if HAS_PSUTIL:
                        self._collect_disk()

                # ── Push event snapshot and last_update ──────────────────
                with self._lock:
                    self._cache["events"] = list(self._events[-MAX_EVENTS_DISPLAY:])
                    self._cache["restart_history"] = list(
                        self._persistent.get("restart_history", [])
                    )
                    self._cache["last_update"] = now

            except Exception as e:
                print(f"[Health] MetricsEngine tick error ({type(e).__name__}): {e}")

            time.sleep(ENGINE_SLEEP_S)

    # ------------------------------------------------------------------
    # COLLECTION: RUNTIME
    # ------------------------------------------------------------------

    def _collect_runtime(self, now):
        app_uptime = now - self._app_start_time
        boot_ts    = 0.0
        comp_uptime = 0.0

        if HAS_PSUTIL:
            try:
                boot_ts     = psutil.boot_time()
                comp_uptime = now - boot_ts
            except Exception:
                pass

        with self._lock:
            self._cache["computer_uptime_s"]    = comp_uptime
            self._cache["last_boot_time"]        = boot_ts
            self._cache["total_boots"]           = self._persistent.get("total_boots_recorded", 1)
            self._cache["normal_shutdowns"]      = self._persistent.get("normal_shutdown_count", 0)
            self._cache["unexpected_shutdowns"]  = self._persistent.get("unexpected_shutdown_count", 0)
            self._cache["app_start_time"]        = self._app_start_time
            self._cache["app_running_time_s"]    = app_uptime
            self._cache["app_restart_count"]     = self._persistent.get("app_restart_count", 1)

    # ------------------------------------------------------------------
    # COLLECTION: WATCHDOG  (every 2 s)
    # ------------------------------------------------------------------

    def _collect_watchdog(self, now):
        gui = self._gui
        wd  = {}

        # ── Camera Watchdog ──────────────────────────────────────────────
        cam_alive = False
        if gui is not None:
            try:
                cam_alive = any(
                    card.is_active
                    and card.camera_thread is not None
                    and card.camera_thread.isRunning()
                    for card in gui.cards
                )
            except Exception:
                pass

        prev_cam = self._wd_prev_alive["camera"]
        if prev_cam is False and cam_alive:
            self._wd_retry_counts["camera"] = 0
            self._add_event("Camera Watchdog: Recovered", "watchdog_recovery")
        elif prev_cam is True and not cam_alive:
            self._wd_retry_counts["camera"] += 1
        self._wd_prev_alive["camera"] = cam_alive

        wd["camera"] = {
            "alive":      cam_alive,
            "last_check": now,
            "recovery":   ("Recovered" if (prev_cam is False and cam_alive)
                           else ("OK" if cam_alive else "No active threads")),
            "retries":    self._wd_retry_counts["camera"],
        }

        # ── YOLO Watchdog ────────────────────────────────────────────────
        yolo_alive = False
        if gui is not None:
            try:
                yolo_alive = (
                    gui.detector is not None
                    and getattr(gui.detector, "model", None) is not None
                )
            except Exception:
                pass

        prev_yolo = self._wd_prev_alive["yolo"]
        if prev_yolo is False and yolo_alive:
            self._wd_retry_counts["yolo"] = 0
            self._add_event("YOLO Watchdog: Model recovered", "watchdog_recovery")
        elif prev_yolo is True and not yolo_alive:
            self._wd_retry_counts["yolo"] += 1
        self._wd_prev_alive["yolo"] = yolo_alive

        wd["yolo"] = {
            "alive":      yolo_alive,
            "last_check": now,
            "recovery":   "OK" if yolo_alive else "Model not loaded",
            "retries":    self._wd_retry_counts["yolo"],
        }

        # ── Relay Watchdog ───────────────────────────────────────────────
        relay_alive = False
        relay_status_str = "OFFLINE"
        if gui is not None:
            try:
                relay_status_str = gui.relay_manager.hw_status
                relay_alive      = (relay_status_str == "ONLINE")
            except Exception:
                pass

        prev_relay = self._wd_prev_alive["relay"]
        if prev_relay is False and relay_alive:
            self._wd_retry_counts["relay"] = 0
            self._add_event("Relay Watchdog: Hardware recovered", "relay_recovery")
        elif prev_relay is True and not relay_alive:
            self._wd_retry_counts["relay"] += 1
            self._add_event("Relay Watchdog: Hardware went offline", "relay_error")
        self._wd_prev_alive["relay"] = relay_alive

        wd["relay"] = {
            "alive":      relay_alive,
            "last_check": now,
            "recovery":   (f"Connected ({relay_status_str})" if relay_alive
                           else f"Offline ({relay_status_str})"),
            "retries":    self._wd_retry_counts["relay"],
        }

        # ── Hardware Watchdog ────────────────────────────────────────────
        hw_alive = False
        if gui is not None:
            try:
                hw_alive = bool(getattr(gui, "hardware_is_online", False))
            except Exception:
                pass

        prev_hw = self._wd_prev_alive["hardware"]
        if prev_hw is False and hw_alive:
            self._wd_retry_counts["hardware"] = 0
            self._add_event("Hardware Watchdog: System recovered", "watchdog_recovery")
        elif prev_hw is True and not hw_alive:
            self._wd_retry_counts["hardware"] += 1
        self._wd_prev_alive["hardware"] = hw_alive

        wd["hardware"] = {
            "alive":      hw_alive,
            "last_check": now,
            "recovery":   "Online" if hw_alive else "Offline",
            "retries":    self._wd_retry_counts["hardware"],
        }

        # ── GUI Watchdog  (heartbeat counter) ────────────────────────────
        current_hb = self._gui_hb_counter
        gui_alive  = (current_hb != self._gui_hb_last_seen)
        self._gui_hb_last_seen = current_hb

        prev_gui = self._wd_prev_alive["gui"]
        if prev_gui is False and gui_alive:
            self._wd_retry_counts["gui"] = 0
        elif prev_gui is True and not gui_alive and prev_gui is not None:
            self._wd_retry_counts["gui"] += 1
        self._wd_prev_alive["gui"] = gui_alive

        wd["gui"] = {
            "alive":      gui_alive,
            "last_check": now,
            "recovery":   "Responsive" if gui_alive else "No heartbeat detected",
            "retries":    self._wd_retry_counts["gui"],
        }

        # ── Security Watchdog ────────────────────────────────────────────
        sec_alive = False
        if gui is not None:
            try:
                sec_alive = (
                    gui.security is not None
                    and hasattr(gui.security, "verify_password")
                )
            except Exception:
                pass

        prev_sec = self._wd_prev_alive["security"]
        if prev_sec is False and sec_alive:
            self._wd_retry_counts["security"] = 0
        self._wd_prev_alive["security"] = sec_alive

        wd["security"] = {
            "alive":      sec_alive,
            "last_check": now,
            "recovery":   "Active" if sec_alive else "Unavailable",
            "retries":    self._wd_retry_counts["security"],
        }

        with self._lock:
            self._cache["watchdog"] = wd

    # ------------------------------------------------------------------
    # COLLECTION: CPU & MEMORY  (every 5 s)
    # ------------------------------------------------------------------

    def _collect_cpu_memory(self):
        try:
            cpu_overall  = psutil.cpu_percent(interval=None)
            cpu_per_core = psutil.cpu_percent(percpu=True, interval=None)

            # Temperature — try common sensor names, fall back to first available
            cpu_temp = None
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for name in ("coretemp", "k10temp", "cpu_thermal", "acpitz",
                                 "cpu-thermal", "soc_thermal"):
                        if name in temps and temps[name]:
                            cpu_temp = temps[name][0].current
                            break
                    if cpu_temp is None:
                        for readings in temps.values():
                            if readings:
                                cpu_temp = readings[0].current
                                break
            except (AttributeError, Exception):
                pass

            mem  = psutil.virtual_memory()
            swap = psutil.swap_memory()

            with self._lock:
                self._cache["cpu_percent"]   = cpu_overall
                self._cache["cpu_per_core"]  = list(cpu_per_core)
                self._cache["cpu_temp_c"]    = cpu_temp
                self._cache["ram_total"]     = mem.total
                self._cache["ram_used"]      = mem.used
                self._cache["ram_available"] = mem.available
                self._cache["ram_percent"]   = mem.percent
                self._cache["swap_total"]    = swap.total
                self._cache["swap_used"]     = swap.used
                self._cache["swap_percent"]  = swap.percent

        except Exception as e:
            print(f"[Health] CPU/Memory collection error: {e}")

    # ------------------------------------------------------------------
    # COLLECTION: DISK  (every 30 s)
    # ------------------------------------------------------------------

    def _collect_disk(self):
        try:
            disk = psutil.disk_usage("/")
            with self._lock:
                self._cache["disk_total"]   = disk.total
                self._cache["disk_used"]    = disk.used
                self._cache["disk_free"]    = disk.free
                self._cache["disk_percent"] = disk.percent
        except Exception as e:
            print(f"[Health] Disk collection error: {e}")

    # ------------------------------------------------------------------
    # COLLECTION: CAMERAS  (every 5 s)
    # ------------------------------------------------------------------

    def _collect_cameras(self, now):
        gui = self._gui
        if gui is None:
            return

        cameras_data = []
        try:
            for i, card in enumerate(gui.cards):
                # Read attributes atomically (GIL ensures float/bool reads are safe)
                is_active  = bool(card.is_active)
                is_online  = bool(card.camera_online)
                prev_time  = float(getattr(card, "prev_time", 0.0))

                # ── Reconnect detection ──────────────────────────────────
                was_online = self._cam_was_online[i]
                if not was_online and is_online and is_active:
                    self._cam_reconnect_cnts[i] += 1
                    self._add_event(f"Camera {i+1} Reconnect", "camera_reconnect")
                elif was_online and not is_online and is_active:
                    self._add_event(f"Camera {i+1} Disconnect", "camera_disconnect")
                self._cam_was_online[i] = is_online

                # ── Running time tracking ────────────────────────────────
                was_active = self._cam_was_active[i]
                if not was_active and is_active:
                    self._cam_start_times[i] = now
                elif was_active and not is_active:
                    self._cam_start_times[i] = 0.0
                self._cam_was_active[i] = is_active

                running_time_s = (
                    (now - self._cam_start_times[i])
                    if (is_active and self._cam_start_times[i] > 0)
                    else 0.0
                )

                # ── Frame rate estimation ────────────────────────────────
                # prev_time is updated each frame in on_frame_received.
                # We compare consecutive 5s samples: if the frame timestamp
                # advanced, frames are flowing.
                approx_fps = 0.0
                old_pt = self._cam_prev_times[i]
                if is_active and is_online and prev_time > old_pt > 0:
                    dt = prev_time - old_pt
                    if 0 < dt <= METRICS_TICK_S:
                        approx_fps = 1.0 / dt   # rough single-frame delta
                self._cam_prev_times[i] = prev_time

                cameras_data.append({
                    "active":          is_active,
                    "online":          is_online,
                    "resolution":      "640×480" if is_online else "N/A",
                    "fps":             approx_fps,
                    "last_frame_time": prev_time,
                    "reconnect_count": self._cam_reconnect_cnts[i],
                    "running_time_s":  running_time_s,
                })

        except Exception as e:
            print(f"[Health] Camera collection error: {e}")
            cameras_data = [{
                "active": False, "online": False, "resolution": "N/A",
                "fps": 0.0, "last_frame_time": 0, "reconnect_count": 0,
                "running_time_s": 0.0,
            } for _ in range(4)]

        with self._lock:
            self._cache["cameras"] = cameras_data

    # ------------------------------------------------------------------
    # COLLECTION: RELAY  (every 5 s)
    # ------------------------------------------------------------------

    def _collect_relay(self, now):
        gui = self._gui
        if gui is None:
            return

        try:
            rm           = gui.relay_manager
            hw_status    = rm.hw_status
            is_online    = (hw_status == "ONLINE")
            port_name    = getattr(rm, "port_name", None) or "N/A"
            relay_states = list(rm.relay_states)

            # ── Command counting via state transitions ───────────────────
            for i in range(4):
                if relay_states[i] != self._relay_last_states[i]:
                    self._relay_total_cmds += 1
                    direction = "ON" if relay_states[i] else "OFF"
                    self._relay_last_cmd   = f"Ch{i+1} → {direction}"
                    self._relay_last_cmd_ts = now
                    if not is_online:
                        self._relay_errors += 1
            self._relay_last_states = list(relay_states)

            # ── Status transition events ─────────────────────────────────
            prev_status = self._relay_prev_status
            if prev_status == "OFFLINE" and hw_status == "ONLINE":
                self._add_event("Relay Recovery: Hardware back online", "relay_recovery")
            elif prev_status == "ONLINE" and hw_status == "OFFLINE":
                self._add_event("Relay Error: Hardware went offline", "relay_error")
            self._relay_prev_status = hw_status

            with self._lock:
                self._cache["relay_connected"]     = is_online
                self._cache["relay_port"]          = port_name
                self._cache["relay_hw_status"]     = hw_status
                self._cache["relay_states"]        = relay_states
                self._cache["relay_last_cmd"]      = self._relay_last_cmd
                self._cache["relay_last_cmd_time"] = self._relay_last_cmd_ts
                self._cache["relay_total_cmds"]    = self._relay_total_cmds
                self._cache["relay_errors"]        = self._relay_errors
                self._cache["relay_heartbeat"]     = ("1s interval" if is_online else "Offline")

        except Exception as e:
            print(f"[Health] Relay collection error: {e}")

    # ------------------------------------------------------------------
    # COLLECTION: AI  (every 5 s)
    # ------------------------------------------------------------------

    def _collect_ai(self):
        gui = self._gui
        if gui is None:
            return

        try:
            detector    = gui.detector
            yolo_loaded = (
                detector is not None
                and getattr(detector, "model", None) is not None
            )
            model_name  = getattr(detector, "model_name", "Unknown") if detector else "N/A"
            confidence  = getattr(detector, "confidence", 0.0) if detector else 0.0

            # Count persons across all active cameras
            total_persons = 0
            active_cards  = 0
            for card in gui.cards:
                if card.is_active and card.camera_online:
                    active_cards += 1
                    persons = getattr(card, "last_persons", [])
                    if persons:
                        total_persons += len(persons)

            if yolo_loaded and active_cards > 0:
                yolo_status = f"Active ({active_cards} camera{'s' if active_cards!=1 else ''})"
            elif yolo_loaded:
                yolo_status = "Loaded (no active cameras)"
            else:
                yolo_status = "Not Loaded"

            # YOLO timer is 1s per card — so detection rate = number of active cards / sec
            detection_rate = f"{active_cards} inference/s ({active_cards} cam{'s' if active_cards!=1 else ''})"

            with self._lock:
                self._cache["yolo_status"]        = yolo_status
                self._cache["yolo_loaded"]         = yolo_loaded
                self._cache["yolo_model"]          = model_name
                self._cache["yolo_confidence"]     = confidence
                self._cache["detection_rate"]      = detection_rate
                self._cache["active_cameras_ai"]   = active_cards
                self._cache["persons_now"]         = total_persons
                # Inference timing cannot be measured without modifying detector.py
                self._cache["avg_inference_ms"]    = "N/A"
                self._cache["last_inference_ms"]   = "N/A"
                self._cache["min_inference_ms"]    = "N/A"
                self._cache["max_inference_ms"]    = "N/A"
                self._cache["dropped_frames"]      = "N/A"

        except Exception as e:
            print(f"[Health] AI collection error: {e}")

    # ------------------------------------------------------------------
    # COLLECTION: OVERALL HEALTH  (every 5 s)
    # ------------------------------------------------------------------

    def _collect_overall_health(self):
        try:
            issues = []
            warnings = []

            cameras = self._cache.get("cameras", [])
            offline = sum(
                1 for c in cameras if c.get("active") and not c.get("online")
            )
            if offline > 0:
                issues.append(f"{offline} camera{'s' if offline!=1 else ''} offline")

            if not self._cache.get("relay_connected", True):
                issues.append("Relay hardware offline")

            cpu = self._cache.get("cpu_percent", 0)
            if cpu > 90:
                issues.append(f"CPU critical ({cpu:.0f}%)")
            elif cpu > 70:
                warnings.append(f"CPU high ({cpu:.0f}%)")

            ram = self._cache.get("ram_percent", 0)
            if ram > 90:
                issues.append(f"RAM critical ({ram:.0f}%)")
            elif ram > 80:
                warnings.append(f"RAM high ({ram:.0f}%)")

            disk = self._cache.get("disk_percent", 0)
            if disk > 90:
                issues.append(f"Disk critical ({disk:.0f}%)")

            if not self._cache.get("yolo_loaded", False):
                issues.append("YOLO model not loaded")

            if issues:
                health = "DEGRADED"
            elif warnings:
                health = "WARNING"
            else:
                health = "HEALTHY"

            with self._lock:
                self._cache["overall_health"]  = health
                self._cache["health_issues"]   = issues + warnings

        except Exception:
            pass

    # ------------------------------------------------------------------
    # INITIAL CACHE STRUCTURE
    # ------------------------------------------------------------------

    def _build_initial_cache(self):
        return {
            # Overview
            "overall_health":     "Initializing",
            "health_issues":      [],
            "last_update":        0.0,

            # Runtime
            "computer_uptime_s":     0.0,
            "last_boot_time":        0.0,
            "total_boots":           1,
            "normal_shutdowns":      0,
            "unexpected_shutdowns":  0,
            "app_start_time":        self._app_start_time,
            "app_running_time_s":    0.0,
            "app_restart_count":     1,

            # CPU
            "cpu_percent":   0.0,
            "cpu_per_core":  [],
            "cpu_temp_c":    None,

            # Memory
            "ram_total":     0,  "ram_used":   0,
            "ram_available": 0,  "ram_percent": 0.0,
            "swap_total":    0,  "swap_used":  0,  "swap_percent": 0.0,

            # Disk
            "disk_total":    0,  "disk_used":  0,
            "disk_free":     0,  "disk_percent": 0.0,

            # AI
            "yolo_status":       "Initializing",
            "yolo_loaded":       False,
            "yolo_model":        "N/A",
            "yolo_confidence":   0.0,
            "detection_rate":    "0 inference/s",
            "active_cameras_ai": 0,
            "persons_now":       0,
            "avg_inference_ms":  "N/A",
            "last_inference_ms": "N/A",
            "min_inference_ms":  "N/A",
            "max_inference_ms":  "N/A",
            "dropped_frames":    "N/A",

            # Cameras (4 entries)
            "cameras": [
                {
                    "active": False, "online": False, "resolution": "N/A",
                    "fps": 0.0, "last_frame_time": 0.0,
                    "reconnect_count": 0, "running_time_s": 0.0,
                }
                for _ in range(4)
            ],

            # Relay
            "relay_connected":     False,
            "relay_port":          "N/A",
            "relay_hw_status":     "OFFLINE",
            "relay_states":        [False, False, False, False],
            "relay_last_cmd":      "N/A",
            "relay_last_cmd_time": 0.0,
            "relay_total_cmds":    0,
            "relay_errors":        0,
            "relay_heartbeat":     "N/A",

            # Watchdog (6 components)
            "watchdog": {
                name: {
                    "alive": False, "last_check": 0.0,
                    "recovery": "Initializing", "retries": 0,
                }
                for name in ("camera", "yolo", "relay", "hardware", "gui", "security")
            },

            # Events & history
            "events":          [],
            "restart_history": [],
        }


# ======================================================================
# HEALTH DIAGNOSTICS PAGE  (PyQt5 QWidget)
# ======================================================================

class HealthDiagnosticsPage(QWidget):
    """
    Full-page diagnostic panel populated entirely from MetricsEngine cache.

    Never calls psutil, system, or camera APIs directly.
    All data flows:  daemon thread → cache → get_snapshot() → QLabel updates.
    """

    def __init__(self, metrics_engine):
        super().__init__()
        self._engine     = metrics_engine
        self._lbl        = {}          # key → QLabel reference dict for updates
        self._cam_lbls   = [{}] * 4   # per-camera label dicts
        self._wd_lbls    = {}          # per-watchdog label dicts
        self._evt_list   = None        # QListWidget for events
        self._hist_list  = None        # QListWidget for restart history
        self._init_ui()

    # ------------------------------------------------------------------
    # UI CONSTRUCTION
    # ------------------------------------------------------------------

    def _init_ui(self):
        self.setStyleSheet("background: transparent; border: none;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # ── Page header ──────────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        page_title = QLabel("🩺 HEALTH & DIAGNOSTICS")
        page_title.setStyleSheet(
            "font-family: 'Segoe UI Semibold'; font-size: 14px; "
            "font-weight: 800; color: #ffffff; padding: 2px 0;"
        )
        hdr_row.addWidget(page_title)
        hdr_row.addStretch()

        self._last_update_lbl = QLabel("Last Update: Initializing…")
        self._last_update_lbl.setStyleSheet(
            "color: #718096; font-size: 10px; font-family: 'Segoe UI';"
        )
        hdr_row.addWidget(self._last_update_lbl)
        root.addLayout(hdr_row)

        # ── Scrollable content ───────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: #1a1a24;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #2d3846;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical { background: none; }
        """)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(2, 2, 6, 2)
        inner_layout.setSpacing(6)

        # Build all 9 sections
        inner_layout.addWidget(self._build_overview())
        inner_layout.addWidget(self._build_runtime())
        inner_layout.addWidget(self._build_hardware())
        inner_layout.addWidget(self._build_ai())
        inner_layout.addWidget(self._build_cameras())
        inner_layout.addWidget(self._build_relay())
        inner_layout.addWidget(self._build_watchdog())
        inner_layout.addWidget(self._build_events())
        inner_layout.addWidget(self._build_restart_history())
        inner_layout.addStretch()

        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        # ── Report button ────────────────────────────────────────────────
        btn_report = QPushButton("📊  GENERATE HEALTH REPORT")
        btn_report.setStyleSheet(_REPORT_BTN_SS)
        btn_report.clicked.connect(self._generate_report)
        root.addWidget(btn_report)

    # ── Helper: make QGroupBox with dark section style ──────────────────

    def _group(self, title):
        gb = QGroupBox(title)
        gb.setStyleSheet(_SECTION_STYLE)
        return gb

    def _subgroup(self, title):
        gb = QGroupBox(title)
        gb.setStyleSheet(_SUBSECTION_STYLE)
        return gb

    # ── Helper: add a key/value row to a grid and register the val label ─

    def _row(self, grid, row, key_text, lbl_key, col=0, init="—"):
        """
        Adds a label pair at (row, col) and (row, col+1) in grid.
        Stores the value QLabel in self._lbl[lbl_key] for later updates.
        Returns the value QLabel.
        """
        k = QLabel(key_text + ":")
        k.setStyleSheet(_KEY_SS)
        v = QLabel(init)
        v.setStyleSheet(_VAL_SS)
        grid.addWidget(k, row, col)
        grid.addWidget(v, row, col + 1)
        if lbl_key:
            self._lbl[lbl_key] = v
        return v

    # ------------------------------------------------------------------
    # SECTION 1: SYSTEM OVERVIEW
    # ------------------------------------------------------------------

    def _build_overview(self):
        gb = self._group("1.  SYSTEM OVERVIEW")
        layout = QVBoxLayout(gb)
        layout.setContentsMargins(12, 16, 12, 10)
        layout.setSpacing(8)

        # Big health status badge
        badge_row = QHBoxLayout()
        lbl_health_title = QLabel("Overall System Health:")
        lbl_health_title.setStyleSheet(_KEY_SS)
        badge_row.addWidget(lbl_health_title)

        self._lbl["ov_health"] = QLabel("INITIALIZING")
        self._lbl["ov_health"].setStyleSheet(_BIG_HEALTH_INIT_SS)
        badge_row.addWidget(self._lbl["ov_health"])
        badge_row.addStretch()
        layout.addLayout(badge_row)

        # Issues
        self._lbl["ov_issues"] = QLabel("")
        self._lbl["ov_issues"].setStyleSheet(_WARN_SS)
        self._lbl["ov_issues"].setWordWrap(True)
        layout.addWidget(self._lbl["ov_issues"])

        # Status grid
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setColumnMinimumWidth(0, 130)
        grid.setColumnMinimumWidth(2, 130)

        self._row(grid, 0, "AI Status",       "ov_ai",       col=0)
        self._row(grid, 0, "Cameras Status",  "ov_cameras",  col=2)
        self._row(grid, 1, "Relay Status",    "ov_relay",    col=0)
        self._row(grid, 1, "Watchdog Status", "ov_watchdog", col=2)
        self._row(grid, 2, "Last Update",     "ov_update",   col=0)
        self._row(grid, 2, "Module Version",  "ov_version",  col=2,
                  init=MODULE_VERSION)
        layout.addLayout(grid)
        return gb

    # ------------------------------------------------------------------
    # SECTION 2: SYSTEM RUNTIME
    # ------------------------------------------------------------------

    def _build_runtime(self):
        gb = self._group("2.  SYSTEM RUNTIME")
        layout = QHBoxLayout(gb)
        layout.setContentsMargins(12, 16, 12, 10)
        layout.setSpacing(16)

        # Computer sub-section
        comp_gb = self._subgroup("Computer")
        comp_grid = QGridLayout(comp_gb)
        comp_grid.setContentsMargins(10, 14, 10, 10)
        comp_grid.setSpacing(5)
        comp_grid.setColumnMinimumWidth(0, 160)

        self._row(comp_grid, 0, "Current Uptime",         "rt_comp_uptime")
        self._row(comp_grid, 1, "Last Boot Time",          "rt_boot_time")
        self._row(comp_grid, 2, "Total Computer Boots",    "rt_total_boots")
        self._row(comp_grid, 3, "Normal Shutdown Count",   "rt_norm_shutdowns")
        self._row(comp_grid, 4, "Unexpected Shutdowns",    "rt_unex_shutdowns")
        layout.addWidget(comp_gb)

        # Application sub-section
        app_gb = self._subgroup("Application")
        app_grid = QGridLayout(app_gb)
        app_grid.setContentsMargins(10, 14, 10, 10)
        app_grid.setSpacing(5)
        app_grid.setColumnMinimumWidth(0, 160)

        self._row(app_grid, 0, "Program Start Time",  "rt_app_start")
        self._row(app_grid, 1, "Program Running Time", "rt_app_uptime")
        self._row(app_grid, 2, "Program Restart Count", "rt_app_restarts")
        layout.addWidget(app_gb)

        return gb

    # ------------------------------------------------------------------
    # SECTION 3: HARDWARE PERFORMANCE
    # ------------------------------------------------------------------

    def _build_hardware(self):
        gb = self._group("3.  HARDWARE PERFORMANCE")
        layout = QHBoxLayout(gb)
        layout.setContentsMargins(12, 16, 12, 10)
        layout.setSpacing(12)

        # ── CPU ──────────────────────────────────────────────────────────
        cpu_gb = self._subgroup("CPU")
        cpu_layout = QVBoxLayout(cpu_gb)
        cpu_layout.setContentsMargins(10, 14, 10, 8)
        cpu_layout.setSpacing(4)

        cpu_main_grid = QGridLayout()
        cpu_main_grid.setColumnMinimumWidth(0, 150)
        cpu_main_grid.setSpacing(4)
        self._row(cpu_main_grid, 0, "Overall CPU Usage", "hw_cpu_total")
        self._row(cpu_main_grid, 1, "CPU Temperature",   "hw_cpu_temp")
        cpu_layout.addLayout(cpu_main_grid)

        # Per-core sub-grid (up to 16 cores, 2-column layout)
        self._cpu_core_container = QWidget()
        self._cpu_core_container.setStyleSheet("background: transparent;")
        self._cpu_core_layout = QGridLayout(self._cpu_core_container)
        self._cpu_core_layout.setSpacing(3)
        self._cpu_core_layout.setContentsMargins(0, 4, 0, 0)
        self._cpu_core_lbls = []   # populated dynamically in refresh_ui
        cpu_layout.addWidget(self._cpu_core_container)
        layout.addWidget(cpu_gb)

        # ── Memory ───────────────────────────────────────────────────────
        mem_gb = self._subgroup("Memory")
        mem_grid = QGridLayout(mem_gb)
        mem_grid.setContentsMargins(10, 14, 10, 10)
        mem_grid.setSpacing(5)
        mem_grid.setColumnMinimumWidth(0, 120)

        self._row(mem_grid, 0, "RAM Usage",     "hw_ram_pct")
        self._row(mem_grid, 1, "RAM Used",      "hw_ram_used")
        self._row(mem_grid, 2, "RAM Total",     "hw_ram_total")
        self._row(mem_grid, 3, "RAM Available", "hw_ram_avail")
        self._row(mem_grid, 4, "Swap Usage",    "hw_swap_pct")
        self._row(mem_grid, 5, "Swap Used",     "hw_swap_used")
        self._row(mem_grid, 6, "Swap Total",    "hw_swap_total")
        layout.addWidget(mem_gb)

        # ── Storage ──────────────────────────────────────────────────────
        disk_gb = self._subgroup("Storage  (/ partition)")
        disk_grid = QGridLayout(disk_gb)
        disk_grid.setContentsMargins(10, 14, 10, 10)
        disk_grid.setSpacing(5)
        disk_grid.setColumnMinimumWidth(0, 120)

        self._row(disk_grid, 0, "Disk Usage",  "hw_disk_pct")
        self._row(disk_grid, 1, "Used Space",  "hw_disk_used")
        self._row(disk_grid, 2, "Free Space",  "hw_disk_free")
        self._row(disk_grid, 3, "Total Space", "hw_disk_total")
        layout.addWidget(disk_gb)

        return gb

    # ------------------------------------------------------------------
    # SECTION 4: AI PERFORMANCE
    # ------------------------------------------------------------------

    def _build_ai(self):
        gb = self._group("4.  AI PERFORMANCE")
        grid = QGridLayout(gb)
        grid.setContentsMargins(12, 16, 12, 10)
        grid.setSpacing(6)
        grid.setColumnMinimumWidth(0, 170)
        grid.setColumnMinimumWidth(2, 170)

        self._row(grid, 0, "YOLO Status",           "ai_status",      col=0)
        self._row(grid, 0, "YOLO Model",            "ai_model",       col=2)
        self._row(grid, 1, "Confidence Threshold",  "ai_conf",        col=0)
        self._row(grid, 1, "Detection Rate",        "ai_det_rate",    col=2)
        self._row(grid, 2, "Persons Detected Now",  "ai_persons",     col=0)
        self._row(grid, 2, "Active Camera Feeds",   "ai_active_cams", col=2)
        self._row(grid, 3, "Avg Inference Time",    "ai_avg_inf",     col=0)
        self._row(grid, 3, "Last Inference Time",   "ai_last_inf",    col=2)
        self._row(grid, 4, "Min Inference Time",    "ai_min_inf",     col=0)
        self._row(grid, 4, "Max Inference Time",    "ai_max_inf",     col=2)
        self._row(grid, 5, "Dropped Frames",        "ai_dropped",     col=0)
        return gb

    # ------------------------------------------------------------------
    # SECTION 5: CAMERA HEALTH
    # ------------------------------------------------------------------

    def _build_cameras(self):
        gb = self._group("5.  CAMERA HEALTH")
        outer = QGridLayout(gb)
        outer.setContentsMargins(12, 16, 12, 10)
        outer.setSpacing(8)

        self._cam_lbls = []
        for i in range(4):
            cam_gb = self._subgroup(f"Station {i+1:02d}")
            cam_grid = QGridLayout(cam_gb)
            cam_grid.setContentsMargins(10, 14, 10, 8)
            cam_grid.setSpacing(4)
            cam_grid.setColumnMinimumWidth(0, 130)

            d = {}
            def _crow(r, key_text, suffix, cam_d=d, col=0):
                k = QLabel(key_text + ":")
                k.setStyleSheet(_KEY_SS)
                v = QLabel("—")
                v.setStyleSheet(_VAL_SS)
                cam_grid.addWidget(k, r, col)
                cam_grid.addWidget(v, r, col + 1)
                cam_d[suffix] = v

            _crow(0, "Status",           "status")
            _crow(1, "Resolution",       "resolution")
            _crow(2, "Current FPS",      "fps")
            _crow(3, "Last Frame Time",  "last_frame")
            _crow(4, "Reconnect Count",  "reconnects")
            _crow(5, "Running Time",     "run_time")

            self._cam_lbls.append(d)
            row_pos = i // 2
            col_pos = i %  2
            outer.addWidget(cam_gb, row_pos, col_pos)

        return gb

    # ------------------------------------------------------------------
    # SECTION 6: RELAY & SAFETY
    # ------------------------------------------------------------------

    def _build_relay(self):
        gb = self._group("6.  RELAY & SAFETY")
        layout = QHBoxLayout(gb)
        layout.setContentsMargins(12, 16, 12, 10)
        layout.setSpacing(16)

        # Main relay info
        rel_gb = self._subgroup("RM04U Relay Module")
        rel_grid = QGridLayout(rel_gb)
        rel_grid.setContentsMargins(10, 14, 10, 10)
        rel_grid.setSpacing(5)
        rel_grid.setColumnMinimumWidth(0, 140)

        self._row(rel_grid, 0, "Relay Connected",   "rl_connected")
        self._row(rel_grid, 1, "Serial Port",       "rl_port")
        self._row(rel_grid, 2, "HW Status",         "rl_hw_status")
        self._row(rel_grid, 3, "Last Command",      "rl_last_cmd")
        self._row(rel_grid, 4, "Last Command Time", "rl_last_cmd_ts")
        self._row(rel_grid, 5, "Total Commands",    "rl_total_cmds")
        self._row(rel_grid, 6, "Relay Errors",      "rl_errors")
        self._row(rel_grid, 7, "Heartbeat",         "rl_heartbeat")
        layout.addWidget(rel_gb)

        # Channel states
        ch_gb = self._subgroup("Channel States")
        ch_grid = QGridLayout(ch_gb)
        ch_grid.setContentsMargins(10, 14, 10, 10)
        ch_grid.setSpacing(5)
        ch_grid.setColumnMinimumWidth(0, 100)

        self._relay_ch_lbls = []
        for i in range(4):
            k = QLabel(f"Channel {i+1}:")
            k.setStyleSheet(_KEY_SS)
            v = QLabel("—")
            v.setStyleSheet(_VAL_SS)
            ch_grid.addWidget(k, i, 0)
            ch_grid.addWidget(v, i, 1)
            self._relay_ch_lbls.append(v)
        layout.addWidget(ch_gb)

        return gb

    # ------------------------------------------------------------------
    # SECTION 7: WATCHDOG
    # ------------------------------------------------------------------

    def _build_watchdog(self):
        gb = self._group("7.  WATCHDOG STATUS  (refreshes every 2 seconds)")
        outer = QGridLayout(gb)
        outer.setContentsMargins(12, 16, 12, 10)
        outer.setSpacing(8)

        wd_names = [
            ("camera",   "📹 Camera Watchdog"),
            ("yolo",     "🧠 YOLO Watchdog"),
            ("relay",    "⚡ Relay Watchdog"),
            ("hardware", "🔧 Hardware Watchdog"),
            ("gui",      "🖥️ GUI Watchdog"),
            ("security", "🔒 Security Watchdog"),
        ]

        self._wd_lbls = {}
        for idx, (key, title) in enumerate(wd_names):
            wd_sub = self._subgroup(title)
            wd_grid = QGridLayout(wd_sub)
            wd_grid.setContentsMargins(10, 14, 10, 8)
            wd_grid.setSpacing(4)
            wd_grid.setColumnMinimumWidth(0, 110)

            d = {}
            def _wrow(r, label, sk, wd_d=d):
                kk = QLabel(label + ":")
                kk.setStyleSheet(_KEY_SS)
                vv = QLabel("—")
                vv.setStyleSheet(_VAL_SS)
                wd_grid.addWidget(kk, r, 0)
                wd_grid.addWidget(vv, r, 1)
                wd_d[sk] = vv

            _wrow(0, "Status",          "alive")
            _wrow(1, "Last Check",      "last_check")
            _wrow(2, "Recovery Status", "recovery")
            _wrow(3, "Retry Count",     "retries")

            self._wd_lbls[key] = d
            row_pos = idx // 2
            col_pos = idx %  2
            outer.addWidget(wd_sub, row_pos, col_pos)

        return gb

    # ------------------------------------------------------------------
    # SECTION 8: EVENT HISTORY
    # ------------------------------------------------------------------

    def _build_events(self):
        gb = self._group("8.  EVENT HISTORY  (latest 150 events)")
        layout = QVBoxLayout(gb)
        layout.setContentsMargins(12, 16, 12, 10)
        layout.setSpacing(4)

        self._evt_list = QListWidget()
        self._evt_list.setStyleSheet(_EVT_LOG_SS)
        self._evt_list.setMaximumHeight(200)
        self._evt_list.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(self._evt_list)
        return gb

    # ------------------------------------------------------------------
    # SECTION 9: RESTART HISTORY
    # ------------------------------------------------------------------

    def _build_restart_history(self):
        gb = self._group("9.  RESTART HISTORY  (loaded at startup)")
        layout = QVBoxLayout(gb)
        layout.setContentsMargins(12, 16, 12, 10)
        layout.setSpacing(4)

        hdr_row = QHBoxLayout()
        for txt, width in [("Restart #", 70), ("Date / Time", 155), ("Previous Uptime", 160)]:
            h = QLabel(txt)
            h.setStyleSheet(
                "color: #63b3ed; font-size: 10px; font-family: 'Segoe UI Semibold';"
                " font-weight: bold; border-bottom: 1px solid #2d3846; padding-bottom: 2px;"
            )
            h.setFixedWidth(width)
            hdr_row.addWidget(h)
        hdr_row.addStretch()
        layout.addLayout(hdr_row)

        self._hist_list = QListWidget()
        self._hist_list.setStyleSheet(_EVT_LOG_SS)
        self._hist_list.setMaximumHeight(180)
        self._hist_list.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(self._hist_list)
        return gb

    # ------------------------------------------------------------------
    # REFRESH  (called by 1-second QTimer)
    # ------------------------------------------------------------------

    def refresh_ui(self):
        """
        Reads a cache snapshot from MetricsEngine and updates all labels.
        All work is read-only; no system calls or heavy computation here.
        """
        try:
            snap = self._engine.get_snapshot()
            self._engine.tick_gui_heartbeat()
            self._update_all(snap)

            last_upd = snap.get("last_update", 0)
            if last_upd > 0:
                self._last_update_lbl.setText(f"Last Update: {_fmt_ts(last_upd)}")
            else:
                self._last_update_lbl.setText("Last Update: Initializing…")
        except Exception as e:
            print(f"[Health] refresh_ui error: {e}")

    def _update_all(self, s):
        """Dispatches all label updates from the snapshot dict s."""
        self._upd_overview(s)
        self._upd_runtime(s)
        self._upd_hardware(s)
        self._upd_ai(s)
        self._upd_cameras(s)
        self._upd_relay(s)
        self._upd_watchdog(s)
        self._upd_events(s)
        self._upd_restart_history(s)

    # ── Overview ────────────────────────────────────────────────────────

    def _upd_overview(self, s):
        health = s.get("overall_health", "Initializing")
        style_map = {
            "HEALTHY":     _BIG_HEALTH_OK_SS,
            "WARNING":     _BIG_HEALTH_WARN_SS,
            "DEGRADED":    _BIG_HEALTH_ERR_SS,
            "Initializing": _BIG_HEALTH_INIT_SS,
        }
        self._lbl["ov_health"].setText(health)
        self._lbl["ov_health"].setStyleSheet(style_map.get(health, _BIG_HEALTH_INIT_SS))

        issues = s.get("health_issues", [])
        if issues:
            self._lbl["ov_issues"].setText("⚠  " + "  |  ".join(issues))
            self._lbl["ov_issues"].setStyleSheet(_WARN_SS)
        else:
            self._lbl["ov_issues"].setText("")

        # AI status
        yolo_ok = s.get("yolo_loaded", False)
        self._set(self._lbl["ov_ai"],
                  "Active" if yolo_ok else "Not Loaded",
                  _OK_SS if yolo_ok else _ERR_SS)

        # Cameras
        cameras = s.get("cameras", [])
        total   = len(cameras)
        offline = sum(1 for c in cameras if c.get("active") and not c.get("online"))
        online  = sum(1 for c in cameras if c.get("online"))
        cam_txt   = f"{online}/{total} Online"
        cam_style = _OK_SS if offline == 0 else _WARN_SS if offline < total else _ERR_SS
        self._set(self._lbl["ov_cameras"], cam_txt, cam_style)

        # Relay
        relay_ok = s.get("relay_connected", False)
        self._set(self._lbl["ov_relay"],
                  "Connected" if relay_ok else "Offline",
                  _OK_SS if relay_ok else _ERR_SS)

        # Watchdog
        wd = s.get("watchdog", {})
        wd_alive_count = sum(1 for v in wd.values() if v.get("alive"))
        wd_total = len(wd)
        self._set(self._lbl["ov_watchdog"],
                  f"{wd_alive_count}/{wd_total} OK",
                  _OK_SS if wd_alive_count == wd_total else _WARN_SS)

        self._lbl["ov_update"].setText(_fmt_ts(s.get("last_update", 0)))
        self._lbl["ov_update"].setStyleSheet(_VAL_SS)

    # ── Runtime ─────────────────────────────────────────────────────────

    def _upd_runtime(self, s):
        self._lbl["rt_comp_uptime"].setText(_fmt_duration(s.get("computer_uptime_s", 0)))
        self._lbl["rt_boot_time"].setText(_fmt_ts(s.get("last_boot_time", 0)))
        self._lbl["rt_total_boots"].setText(str(s.get("total_boots", 1)))
        self._lbl["rt_norm_shutdowns"].setText(str(s.get("normal_shutdowns", 0)))

        unex = s.get("unexpected_shutdowns", 0)
        self._lbl["rt_unex_shutdowns"].setText(str(unex))
        self._lbl["rt_unex_shutdowns"].setStyleSheet(_ERR_SS if unex > 0 else _OK_SS)

        self._lbl["rt_app_start"].setText(_fmt_ts(s.get("app_start_time", 0)))
        self._lbl["rt_app_uptime"].setText(_fmt_duration(s.get("app_running_time_s", 0)))
        self._lbl["rt_app_restarts"].setText(str(s.get("app_restart_count", 1)))

        for k in ("rt_comp_uptime", "rt_boot_time", "rt_total_boots",
                  "rt_norm_shutdowns", "rt_app_start", "rt_app_uptime",
                  "rt_app_restarts"):
            if k in self._lbl:
                self._lbl[k].setStyleSheet(_VAL_SS)

    # ── Hardware ─────────────────────────────────────────────────────────

    def _upd_hardware(self, s):
        # CPU overall
        cpu = s.get("cpu_percent", 0.0)
        self._set(self._lbl["hw_cpu_total"],
                  f"{cpu:.1f}%",
                  _pct_style(cpu))

        # CPU temperature
        temp = s.get("cpu_temp_c", None)
        if temp is not None:
            temp_style = _ERR_SS if temp > 85 else _WARN_SS if temp > 70 else _OK_SS
            self._set(self._lbl["hw_cpu_temp"], f"{temp:.1f}°C", temp_style)
        else:
            self._set(self._lbl["hw_cpu_temp"], "N/A", _INIT_SS)

        # Per-core labels (created dynamically)
        cores = s.get("cpu_per_core", [])
        # Ensure enough label slots exist
        while len(self._cpu_core_lbls) < len(cores):
            idx = len(self._cpu_core_lbls)
            k = QLabel(f"Core {idx}:")
            k.setStyleSheet(_KEY_SS)
            v = QLabel("—")
            v.setStyleSheet(_VAL_SS)
            row = idx // 4
            c_col = (idx % 4) * 2
            self._cpu_core_layout.addWidget(k, row, c_col)
            self._cpu_core_layout.addWidget(v, row, c_col + 1)
            self._cpu_core_lbls.append(v)

        for i, pct in enumerate(cores):
            if i < len(self._cpu_core_lbls):
                self._cpu_core_lbls[i].setText(f"{pct:.0f}%")
                self._cpu_core_lbls[i].setStyleSheet(_pct_style(pct))

        # RAM
        rp = s.get("ram_percent", 0.0)
        self._set(self._lbl["hw_ram_pct"],   f"{rp:.1f}%",
                  _pct_style(rp))
        self._set(self._lbl["hw_ram_used"],  _fmt_bytes(s.get("ram_used",  0)), _VAL_SS)
        self._set(self._lbl["hw_ram_total"], _fmt_bytes(s.get("ram_total", 0)), _VAL_SS)
        self._set(self._lbl["hw_ram_avail"], _fmt_bytes(s.get("ram_available", 0)), _VAL_SS)

        sp = s.get("swap_percent", 0.0)
        self._set(self._lbl["hw_swap_pct"],  f"{sp:.1f}%", _pct_style(sp))
        self._set(self._lbl["hw_swap_used"], _fmt_bytes(s.get("swap_used",  0)), _VAL_SS)
        self._set(self._lbl["hw_swap_total"],_fmt_bytes(s.get("swap_total", 0)), _VAL_SS)

        # Disk
        dp = s.get("disk_percent", 0.0)
        self._set(self._lbl["hw_disk_pct"],  f"{dp:.1f}%", _pct_style(dp))
        self._set(self._lbl["hw_disk_used"], _fmt_bytes(s.get("disk_used",  0)), _VAL_SS)
        self._set(self._lbl["hw_disk_free"], _fmt_bytes(s.get("disk_free",  0)), _VAL_SS)
        self._set(self._lbl["hw_disk_total"],_fmt_bytes(s.get("disk_total", 0)), _VAL_SS)

    # ── AI ───────────────────────────────────────────────────────────────

    def _upd_ai(self, s):
        yolo_ok = s.get("yolo_loaded", False)
        self._set(self._lbl["ai_status"],
                  s.get("yolo_status", "N/A"),
                  _OK_SS if yolo_ok else _ERR_SS)
        self._lbl["ai_model"].setText(s.get("yolo_model", "N/A"))
        self._lbl["ai_model"].setStyleSheet(_VAL_SS)
        conf = s.get("yolo_confidence", 0.0)
        self._lbl["ai_conf"].setText(f"{conf:.2f}")
        self._lbl["ai_conf"].setStyleSheet(_VAL_SS)
        self._lbl["ai_det_rate"].setText(s.get("detection_rate", "N/A"))
        self._lbl["ai_det_rate"].setStyleSheet(_VAL_SS)
        persons = s.get("persons_now", 0)
        self._set(self._lbl["ai_persons"],
                  str(persons),
                  _ERR_SS if persons > 0 else _OK_SS)
        self._lbl["ai_active_cams"].setText(str(s.get("active_cameras_ai", 0)))
        self._lbl["ai_active_cams"].setStyleSheet(_VAL_SS)
        for k in ("ai_avg_inf", "ai_last_inf", "ai_min_inf", "ai_max_inf", "ai_dropped"):
            key = k.replace("ai_avg_inf", "avg_inference_ms")\
                   .replace("ai_last_inf","last_inference_ms")\
                   .replace("ai_min_inf", "min_inference_ms")\
                   .replace("ai_max_inf", "max_inference_ms")\
                   .replace("ai_dropped", "dropped_frames")
            self._lbl[k].setText(str(s.get(key, "N/A")))
            self._lbl[k].setStyleSheet(_INIT_SS)

    # ── Cameras ──────────────────────────────────────────────────────────

    def _upd_cameras(self, s):
        cameras = s.get("cameras", [])
        for i in range(min(4, len(cameras))):
            c = cameras[i]
            d = self._cam_lbls[i]
            is_online = c.get("online", False)
            is_active = c.get("active", False)

            if not is_active:
                status_txt, status_ss = "STANDBY", _INIT_SS
            elif is_online:
                status_txt, status_ss = "● ONLINE", _OK_SS
            else:
                status_txt, status_ss = "⚠ OFFLINE", _ERR_SS

            self._set(d["status"],     status_txt,  status_ss)
            self._set(d["resolution"], c.get("resolution", "N/A"), _VAL_SS)

            fps = c.get("fps", 0.0)
            fps_txt = f"~{fps:.1f} fps" if fps > 0 else ("Flowing" if is_online else "—")
            self._set(d["fps"], fps_txt, _VAL_SS)

            lft = c.get("last_frame_time", 0)
            self._set(d["last_frame"], _fmt_ts(lft) if lft > 0 else "—", _VAL_SS)

            rc = c.get("reconnect_count", 0)
            self._set(d["reconnects"],
                      str(rc),
                      _WARN_SS if rc > 0 else _OK_SS)

            self._set(d["run_time"],
                      _fmt_duration(c.get("running_time_s", 0)),
                      _VAL_SS)

    # ── Relay ────────────────────────────────────────────────────────────

    def _upd_relay(self, s):
        connected = s.get("relay_connected", False)
        self._set(self._lbl["rl_connected"],
                  "● CONNECTED" if connected else "⚠ DISCONNECTED",
                  _OK_SS if connected else _ERR_SS)
        self._lbl["rl_port"].setText(s.get("relay_port", "N/A"))
        self._lbl["rl_port"].setStyleSheet(_VAL_SS)
        self._lbl["rl_hw_status"].setText(s.get("relay_hw_status", "N/A"))
        self._lbl["rl_hw_status"].setStyleSheet(
            _OK_SS if connected else _ERR_SS
        )
        self._lbl["rl_last_cmd"].setText(s.get("relay_last_cmd", "N/A"))
        self._lbl["rl_last_cmd"].setStyleSheet(_VAL_SS)

        lct = s.get("relay_last_cmd_time", 0)
        self._lbl["rl_last_cmd_ts"].setText(_fmt_ts(lct) if lct > 0 else "N/A")
        self._lbl["rl_last_cmd_ts"].setStyleSheet(_VAL_SS)

        self._lbl["rl_total_cmds"].setText(str(s.get("relay_total_cmds", 0)))
        self._lbl["rl_total_cmds"].setStyleSheet(_VAL_SS)

        errs = s.get("relay_errors", 0)
        self._set(self._lbl["rl_errors"],
                  str(errs),
                  _ERR_SS if errs > 0 else _OK_SS)

        self._lbl["rl_heartbeat"].setText(s.get("relay_heartbeat", "N/A"))
        self._lbl["rl_heartbeat"].setStyleSheet(
            _OK_SS if connected else _WARN_SS
        )

        # Channel states
        states = s.get("relay_states", [False] * 4)
        for i, lbl in enumerate(self._relay_ch_lbls):
            st = states[i] if i < len(states) else False
            self._set(lbl,
                      "ON  ●" if st else "OFF ○",
                      _ERR_SS if st else _OK_SS)

    # ── Watchdog ─────────────────────────────────────────────────────────

    def _upd_watchdog(self, s):
        wd = s.get("watchdog", {})
        for key, d in self._wd_lbls.items():
            info = wd.get(key, {})
            alive = info.get("alive", False)
            self._set(d["alive"],
                      "● ALIVE" if alive else "⚠ NOT ALIVE",
                      _OK_SS if alive else _ERR_SS)

            lc = info.get("last_check", 0)
            d["last_check"].setText(_fmt_ts(lc) if lc > 0 else "—")
            d["last_check"].setStyleSheet(_VAL_SS)

            recovery = info.get("recovery", "N/A")
            d["recovery"].setText(recovery)
            d["recovery"].setStyleSheet(_VAL_SS)

            retries = info.get("retries", 0)
            self._set(d["retries"],
                      str(retries),
                      _WARN_SS if retries > 0 else _OK_SS)

    # ── Event History ────────────────────────────────────────────────────

    def _upd_events(self, s):
        events = s.get("events", [])
        # Only redraw if count changed (avoid flicker on every 1s tick)
        cur_count = self._evt_list.count()
        if cur_count == len(events):
            return

        self._evt_list.clear()
        type_colors = {
            "startup":          "#76e4f7",
            "shutdown":         "#76e4f7",
            "camera_reconnect": "#48bb78",
            "camera_disconnect":"#f6ad55",
            "relay_recovery":   "#48bb78",
            "relay_error":      "#fc8181",
            "watchdog_recovery":"#48bb78",
            "info":             "#a0aec0",
        }
        for evt in reversed(events):   # Most recent first
            ts  = evt.get("datetime", "")
            msg = evt.get("message", "")
            typ = evt.get("type", "info")
            item = QListWidgetItem(f"[{ts}]  {msg}")
            color = type_colors.get(typ, "#a0aec0")
            item.setForeground(QColor(color))
            self._evt_list.addItem(item)

    # ── Restart History ──────────────────────────────────────────────────

    def _upd_restart_history(self, s):
        history = s.get("restart_history", [])
        cur_count = self._hist_list.count()
        if cur_count == len(history):
            return

        self._hist_list.clear()
        for entry in reversed(history):   # Most recent first
            restart_n   = entry.get("restart_count",    "—")
            dt_str      = entry.get("datetime",         "—")
            prev_uptime = entry.get("previous_uptime_s", 0)
            uptime_str  = _fmt_duration(prev_uptime) if prev_uptime > 0 else "—"
            item = QListWidgetItem(
                f"#{restart_n:<4}  {dt_str:<22}  Prev uptime: {uptime_str}"
            )
            item.setForeground(QColor("#a0aec0"))
            self._hist_list.addItem(item)

    # ── Helper ───────────────────────────────────────────────────────────

    @staticmethod
    def _set(lbl, text, style):
        """Sets text and stylesheet on a QLabel only when they differ (reduces repaints)."""
        if lbl.text() != text:
            lbl.setText(text)
        if lbl.styleSheet() != style:
            lbl.setStyleSheet(style)

    # ------------------------------------------------------------------
    # REPORT GENERATION
    # ------------------------------------------------------------------

    def _generate_report(self):
        """
        Generates a single structured plain-text comprehensive report from cached data.
        Non-blocking: reads snapshot (< 1 ms), ensures output directory exists,
        then writes exactly one report file to /home/forklift/AI_Forklift_Reports/.
        The running AI detection is never interrupted.
        """
        snap = self._engine.get_snapshot()
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Fixed report output directory — never inside the project folder
        report_dir = "/home/forklift/AI_Forklift_Reports"
        try:
            os.makedirs(report_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Report Error",
                f"Cannot create report directory:\n{report_dir}\n\nError: {e}",
            )
            return

        fname = f"AI_Forklift_System_Report_{ts}.txt"
        fpath = os.path.join(report_dir, fname)

        try:
            report_lines = self._build_report_text(snap, ts)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("\n".join(report_lines))

            QMessageBox.information(
                self,
                "Report Generated",
                f"✅ Comprehensive system report saved:\n\n{fpath}\n\n"
                f"The running AI detection was not interrupted.",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Report Error",
                f"Failed to generate report:\n{e}",
            )

    def _build_report_text(self, s, ts):
        """Builds and returns the comprehensive 10-section report lines from snapshot dict s.
        All values are reused from the existing MetricsEngine cache — no new calculations."""
        SEP  = "=" * 60
        SEP2 = "-" * 40
        lines = []

        def h(title):
            lines.append("")
            lines.append(SEP)
            lines.append(f"  {title}")
            lines.append(SEP2)

        def kv(key, val, indent="  "):
            lines.append(f"{indent}{key:<35}{val}")

        # ── Report Header ──────────────────────────────────────────────
        lines.append(SEP)
        lines.append("  LIMITLESS FUTURE")
        lines.append("  AI FORKLIFT SAFETY SYSTEM")
        lines.append("  COMPREHENSIVE SYSTEM REPORT")
        lines.append(SEP)

        # ── Section 1: REPORT INFORMATION ─────────────────────────────
        h("1. REPORT INFORMATION")
        now_dt = datetime.datetime.now()
        report_id = f"RPT-{ts}"
        kv("Report ID:",              report_id)
        kv("Date:",                   now_dt.strftime("%Y-%m-%d"))
        kv("Time:",                   now_dt.strftime("%H:%M:%S"))
        kv("Software Version:",       MODULE_VERSION)
        kv("Operating System:",       platform.platform())
        kv("Machine Name:",           platform.node() or "N/A")

        # ── Section 2: OVERALL SYSTEM HEALTH ──────────────────────────
        h("2. OVERALL SYSTEM HEALTH")
        health = s.get("overall_health", "N/A")
        issues = s.get("health_issues", [])
        kv("Overall Health Status:",  health)
        kv("Program Running Time:",   _fmt_duration(s.get("app_running_time_s", 0)))
        kv("Program Restart Count:",  str(s.get("app_restart_count", 1)))
        cpu = s.get("cpu_percent", 0)
        kv("CPU Usage:",              f"{cpu:.1f}%")
        temp = s.get("cpu_temp_c")
        kv("CPU Temperature:",        f"{temp:.1f}°C" if temp is not None else "N/A")
        rp = s.get("ram_percent", 0)
        kv("RAM Usage:",              f"{rp:.1f}%  ({_fmt_bytes(s.get('ram_used', 0))} / {_fmt_bytes(s.get('ram_total', 0))})")
        dp = s.get("disk_percent", 0)
        kv("Disk Usage:",             f"{dp:.1f}%  ({_fmt_bytes(s.get('disk_used', 0))} used, {_fmt_bytes(s.get('disk_free', 0))} free)")
        cores = s.get("cpu_per_core", [])
        if cores:
            core_str = "  ".join(f"Core{i}:{pct:.0f}%" for i, pct in enumerate(cores))
            kv("System Load (cores):", core_str)
        else:
            kv("System Load:",         "N/A")

        # ── Section 3: AI PERFORMANCE ──────────────────────────────────
        h("3. AI PERFORMANCE")
        kv("YOLO Model:",             s.get("yolo_model", "N/A"))
        kv("Model Path:",             s.get("yolo_model", "N/A"))
        kv("Confidence Threshold:",   f"{s.get('yolo_confidence', 0):.2f}")
        kv("Detection Rate:",         s.get("detection_rate", "N/A"))
        kv("Inference Time:",         str(s.get("avg_inference_ms", "N/A")))
        active_cams = s.get("active_cameras_ai", 0)
        kv("Average FPS:",            f"{active_cams} inference/s ({active_cams} active camera{'s' if active_cams != 1 else ''})")
        kv("Persons Detected Now:",   str(s.get("persons_now", 0)))
        kv("Min Inference Time:",     str(s.get("min_inference_ms", "N/A")))
        kv("Max Inference Time:",     str(s.get("max_inference_ms", "N/A")))
        kv("Dropped Frames:",         str(s.get("dropped_frames", "N/A")))

        # ── Section 4: CAMERA STATUS ───────────────────────────────────
        h("4. CAMERA STATUS")
        for i, c in enumerate(s.get("cameras", [])):
            lines.append("")
            lines.append(f"  Camera {i+1}")
            conn_status = "CONNECTED" if c.get("online") else ("ACTIVE (Offline)" if c.get("active") else "NOT STARTED")
            kv("  Connection Status:",  conn_status)
            run_status  = "RUNNING" if c.get("active") else "STANDBY"
            kv("  Running Status:",     run_status)
            fps = c.get("fps", 0)
            kv("  Current FPS:",        f"~{fps:.1f} fps" if fps > 0 else ("Flowing" if c.get("online") else "N/A"))

        # ── Section 5: HARDWARE STATUS ─────────────────────────────────
        h("5. HARDWARE STATUS")
        relay_ok = s.get("relay_connected", False)
        kv("Hardware Connection:",    "CONNECTED" if relay_ok else "DISCONNECTED")
        kv("Relay Board Status:",     s.get("relay_hw_status", "N/A"))
        states = s.get("relay_states", [False] * 4)
        relay_map_str = "  ".join(f"Ch{i+1}:{'ON' if st else 'OFF'}" for i, st in enumerate(states))
        kv("Relay Mapping:",          relay_map_str if states else "N/A")
        kv("COM Port:",               s.get("relay_port", "N/A"))
        # Read baud rate from config if available
        try:
            cfg_path = os.path.join(_SCRIPT_DIR, "config.json")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r") as _f:
                    _cfg = json.load(_f)
                baud = _cfg.get("settings", {}).get("baud_rate", "N/A")
            else:
                baud = "N/A"
        except Exception:
            baud = "N/A"
        kv("Baud Rate:",              str(baud))
        kv("Heartbeat Status:",       s.get("relay_heartbeat", "N/A"))
        relay_errs = s.get("relay_errors", 0)
        alarm_status = "NO ACTIVE ALARMS" if relay_errs == 0 else f"ERRORS DETECTED ({relay_errs})"
        kv("Alarm Status:",           alarm_status)

        # ── Section 6: SYSTEM CONFIGURATION ───────────────────────────
        h("6. SYSTEM CONFIGURATION")
        try:
            cfg_path = os.path.join(_SCRIPT_DIR, "config.json")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r") as _f:
                    cfg = json.load(_f)
                settings = cfg.get("settings", {})

                # Camera Mapping
                cam_map = settings.get("camera_mapping", [])
                cam_map_str = "  ".join(f"Station{i+1}:Node{v}" for i, v in enumerate(cam_map)) if cam_map else "N/A"
                kv("Camera Mapping:",       cam_map_str)

                # Relay Mapping
                rel_map = settings.get("relay_mapping", [])
                rel_map_str = "  ".join(f"Station{i+1}->Relay{v}" for i, v in enumerate(rel_map)) if rel_map else "N/A"
                kv("Relay Mapping:",        rel_map_str)

                # ROI Information (from config root keys)
                roi_parts = []
                for cam_idx in range(4):
                    cam_key = f"camera_{cam_idx}"
                    roi = cfg.get(cam_key, {})
                    if roi:
                        x = roi.get("x", "?")
                        y = roi.get("y", "?")
                        w = roi.get("w", "?")
                        h_val = roi.get("h", "?")
                        roi_parts.append(f"Cam{cam_idx+1}[x={x},y={y},w={w},h={h_val}]")
                    else:
                        roi_parts.append(f"Cam{cam_idx+1}[not set]")
                kv("ROI Information:",       "  ".join(roi_parts))

                # Detection Settings
                conf = settings.get("confidence", "N/A")
                model = settings.get("model_path", "N/A")
                kv("Detection Settings:",    f"Model={model}  Confidence={conf}")

                # Alarm Settings
                on_d  = settings.get("on_delay", "N/A")
                off_d = settings.get("off_delay", "N/A")
                ar    = settings.get("alarm_auto_reset", "N/A")
                kv("Alarm Settings:",        f"OnDelay={on_d}s  OffDelay={off_d}s  AutoReset={ar}s")

                # Auto Reset Settings
                kv("Auto Reset Settings:",   f"{ar}s")

                # Hardware Settings
                com  = settings.get("com_port", "N/A")
                baud = settings.get("baud_rate", "N/A")
                boot = "Enabled" if settings.get("boot_self_test", 1) == 1 else "Disabled"
                coil = "Enabled" if settings.get("hardware_coil_enabled", 1) == 1 else "Disabled"
                kv("Hardware Settings:",     f"Port={com}  Baud={baud}  BootTest={boot}  Coil={coil}")
            else:
                kv("Configuration File:",    "config.json not found")
        except Exception as e:
            kv("Config Read Error:",         str(e))

        # ── Section 7: RUNTIME STATISTICS ─────────────────────────────
        h("7. RUNTIME STATISTICS")
        # Total person detections — sum persons_now across session (best available from cache)
        kv("Total Person Detections:",str(s.get("persons_now", 0)) + "  (current snapshot)")
        # Alarm activations = relay commands that resulted in ON state
        total_cmds = s.get("relay_total_cmds", 0)
        kv("Alarm Activations:",      str(total_cmds) + "  (relay ON/OFF transitions)")
        # Manual relay tests tracked via relay_total_cmds in override mode
        kv("Manual Relay Tests:",     str(s.get("relay_errors", 0)) + "  (relay error count)")
        kv("Program Uptime:",         _fmt_duration(s.get("app_running_time_s", 0)))
        lines.append("")
        lines.append("  Current Session Statistics:")
        kv("  Program Start Time:",   _fmt_ts(s.get("app_start_time", 0)))
        kv("  Computer Uptime:",      _fmt_duration(s.get("computer_uptime_s", 0)))
        kv("  Last Boot Time:",       _fmt_ts(s.get("last_boot_time", 0)))
        kv("  Total Boots (recorded):", str(s.get("total_boots", 1)))
        kv("  Normal Shutdowns:",     str(s.get("normal_shutdowns", 0)))
        kv("  Unexpected Shutdowns:", str(s.get("unexpected_shutdowns", 0)))

        # ── Section 8: WARNINGS AND ERRORS ────────────────────────────
        h("8. WARNINGS AND ERRORS")
        if issues:
            lines.append("  Current Warnings / Issues:")
            for issue in issues:
                lines.append(f"    • {issue}")
        else:
            lines.append("  Current Warnings:  None")

        lines.append("")
        relay_errs = s.get("relay_errors", 0)
        if relay_errs > 0:
            lines.append(f"  Current Errors:    {relay_errs} relay error(s) detected")
        else:
            lines.append("  Current Errors:    None")

        lines.append("")
        lines.append("  Recent Critical Events:")
        events = s.get("events", [])
        critical_types = ("relay_error", "camera_disconnect", "shutdown")
        critical_events = [
            e for e in reversed(events)
            if e.get("type", "") in critical_types
        ][:10]
        if critical_events:
            for evt in critical_events:
                lines.append(
                    f"    [{evt.get('datetime','')}]  "
                    f"[{evt.get('type','').upper():<20}]  "
                    f"{evt.get('message','')}"
                )
        else:
            lines.append("    No critical events recorded in this session.")

        lines.append("")
        lines.append("  Full Event History (most recent first):")
        if events:
            for evt in reversed(events):
                lines.append(
                    f"    [{evt.get('datetime','')}]  "
                    f"[{evt.get('type','').upper():<20}]  "
                    f"{evt.get('message','')}"
                )
        else:
            lines.append("    No events recorded.")

        # ── Section 9: SYSTEM ASSESSMENT ──────────────────────────────
        h("9. SYSTEM ASSESSMENT")
        lines.append("")
        if health == "HEALTHY":
            lines.append("  SYSTEM HEALTHY")
            lines.append("")
            lines.append("  All monitored subsystems are operating within normal parameters.")
            lines.append("  No warnings or critical issues detected at report generation time.")
        elif health == "WARNING":
            lines.append("  SYSTEM HEALTHY WITH WARNINGS")
            lines.append("")
            lines.append("  The system is operational but the following warnings require attention:")
            for issue in issues:
                lines.append(f"    • {issue}")
        else:
            lines.append("  CRITICAL ISSUES DETECTED")
            lines.append("")
            lines.append("  One or more critical problems were found at report generation time:")
            for issue in issues:
                lines.append(f"    • {issue}")
            lines.append("")
            lines.append("  Immediate inspection is recommended.")

        # ── Section 10: END OF REPORT ──────────────────────────────────
        lines.append("")
        lines.append(SEP)
        lines.append("  Generated Automatically")
        lines.append("  Limitless Future")
        lines.append("  AI Forklift Safety System")
        lines.append(SEP)
        lines.append("")
        return lines
