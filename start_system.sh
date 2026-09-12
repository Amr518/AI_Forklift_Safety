#!/bin/bash
# ============================================================
# Limitless Future — Forklift Safety System Launcher
# ============================================================
# Socket IPC Architecture
#   hardware_worker.py  →  Unix Domain Socket SERVER
#   ai_gui_system.py    →  Unix Domain Socket CLIENT
#   IPC Endpoint        →  /dev/shm/forklift_relay.sock
# ============================================================

# 1. Hardware and USB Bus Stabilization Delay (15 seconds)
# Allow Linux kernel, V4L2 subsystem, and USB serial drivers sufficient time
# to enumerate all cameras and hardware peripherals upon system boot/startup.
STARTUP_DELAY=15
if [ "${SKIP_DELAY:-0}" -eq 1 ] || [ "$1" == "--no-delay" ]; then
    echo "[LAUNCHER] Skipping hardware stabilization delay (flag detected)."
else
    echo "[LAUNCHER] ============================================================"
    echo "[LAUNCHER] Waiting 15s for Linux kernel to detect all hardware & USB devices..."
    echo "[LAUNCHER] ============================================================"
    for ((sec=STARTUP_DELAY; sec>0; sec--)); do
        if (( sec % 5 == 0 || sec <= 3 )); then
            echo "[LAUNCHER] Hardware discovery settling: ${sec}s remaining..."
        fi
        sleep 1
    done
    echo "[LAUNCHER] Hardware stabilization complete. Proceeding with launch..."
fi

# 2. Display server access for the current user session
export DISPLAY="${DISPLAY:-:0}"
if [ -z "$XAUTHORITY" ] || [ ! -f "$XAUTHORITY" ]; then
    if [ -f "/run/user/$(id -u)/gdm/Xauthority" ]; then
        export XAUTHORITY="/run/user/$(id -u)/gdm/Xauthority"
    elif [ -f "$HOME/.Xauthority" ]; then
        export XAUTHORITY="$HOME/.Xauthority"
    fi
fi
xhost +SI:localuser:$USER >> /dev/null 2>&1


# 3. Kill any orphaned hardware worker from a previous session
pkill -f hardware_worker.py 2>/dev/null
sleep 0.5

# 4. Remove stale IPC socket and lock files
rm -f /dev/shm/forklift_relay.sock /dev/shm/*.sock /tmp/hardware_worker.lock /tmp/*.lock

# 5. Enter project directory and activate virtual environment
cd "$HOME/Desktop/AI_Forklift_Safety" || {
    echo "[LAUNCHER] FATAL: Project directory not found. Aborting."
    exit 1
}
source venv/bin/activate

# 6. Launch Hardware Worker (IPC server) in background
python3 hardware_worker.py &
HW_PID=$!
echo "[LAUNCHER] Hardware worker started (PID: $HW_PID)"

# 7. Wait for socket readiness instead of a fixed sleep.
#    Polls every 0.5s for up to 15 seconds, covering the CH340 firmware
#    stabilisation delay (2s) and boot self-test (4ch × 2 × 0.3s = 2.4s).
SOCKET_PATH="/dev/shm/forklift_relay.sock"
WAIT=0
while [ ! -S "$SOCKET_PATH" ] && [ "$WAIT" -lt 30 ]; do
    sleep 0.5
    WAIT=$((WAIT + 1))
done

if [ ! -S "$SOCKET_PATH" ]; then
    echo "[LAUNCHER] ERROR: Hardware worker socket not ready after 15s. Aborting."
    kill "$HW_PID" 2>/dev/null
    exit 1
fi

echo "[LAUNCHER] Socket ready. Launching GUI..."

# 8. Launch the AI GUI (Socket IPC Client) in fullscreen kiosk mode
export QT_QPA_PLATFORM=xcb
python3 ai_gui_system.py
EXIT_CODE=$?

# 9. Cleanup on GUI exit — terminate background worker and remove socket
kill "$HW_PID" 2>/dev/null
pkill -f hardware_worker.py 2>/dev/null
rm -f /dev/shm/forklift_relay.sock /dev/shm/*.sock /tmp/hardware_worker.lock
echo "[LAUNCHER] System shutdown complete (code $EXIT_CODE)."
exit $EXIT_CODE
