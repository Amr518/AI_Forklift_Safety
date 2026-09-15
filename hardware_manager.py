"""
============================================================
Forklift AI Safety System — Hardware Manager (Socket IPC Client)
============================================================
Communicates with hardware_worker.py via a Unix Domain Socket.

Architecture Role: IPC CLIENT (PRODUCER)
  - Connects to /dev/shm/forklift_relay.sock with infinite auto-reconnect
  - Sends trigger commands, config updates, and relay mappings
  - Receives hardware status updates pushed by the server
  - Exposes hw_status as a cached thread-safe property

IPC Protocol (JSON-over-newline):
  Client → Server:
    {"cmd":"trigger","station":1,"state":1,"manual":true}
    {"cmd":"config","on_delay":0.2,"off_delay":1.5,...}
    {"cmd":"relay_mapping","mapping":[3,2,3,2]}
    {"cmd":"manual_test","enabled":1}
    {"cmd":"connect",...}
    {"cmd":"disconnect"}
    {"cmd":"status"}
  Server → Client:
    {"type":"status","hw_status":"ONLINE"}
    {"type":"ack","cmd":"trigger","success":true}
============================================================
"""

import os
import json
import time
import glob
import socket
import threading

try:
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

SOCKET_PATH       = "/dev/shm/forklift_relay.sock"
DEFAULT_ON_DELAY  = 0.2
DEFAULT_OFF_DELAY = 1.5


class USBRelayManager:
    """
    Socket IPC Client for the 4-Channel USB Relay module (RM04U).

    Sends JSON commands to hardware_worker.py over a Unix Domain Socket.
    The actual serial connection is owned entirely by hardware_worker.py.
    Public API is backward-compatible with the JSON-bridge version.
    """

    def __init__(self):
        self.port_name    = None
        self.is_connected = False
        self.relay_states  = [False, False, False, False]
        self.last_cmd_time = [0.0, 0.0, 0.0, 0.0]

        self.on_delay              = DEFAULT_ON_DELAY
        self.off_delay             = DEFAULT_OFF_DELAY
        self.boot_self_test        = 1
        self.hardware_coil_enabled = 1
        self.manual_overrides      = [False, False, False, False]

        self._socket       = None
        self._socket_lock  = threading.Lock()
        self._recv_thread  = None
        self._recv_running = True   # False only when cleanup() is called

        self._hw_status      = "OFFLINE"
        self._hw_status_lock = threading.Lock()

        self._start_connection()

    # ==========================================
    # SOCKET IPC CONNECTION MANAGEMENT
    # ==========================================

    def _start_connection(self):
        """Fires a background connection attempt to the IPC server."""
        threading.Thread(target=self._connect_socket, daemon=True).start()

    def _connect_socket(self):
        """
        Connects to the hardware worker socket, retrying with 0.5s backoff
        until the connection succeeds or cleanup() signals shutdown.
        Replaces the original 30-attempt hard cap (which left the client
        permanently disconnected after 15 seconds with no recovery path).
        """
        while self._recv_running:
            with self._socket_lock:
                if self._socket is not None:
                    return True  # Already connected (e.g. by a parallel call)

            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(SOCKET_PATH)

                with self._socket_lock:
                    self._socket = sock

                print(f"[USBRelayManager] Connected to IPC server: {SOCKET_PATH}")

                self._recv_thread = threading.Thread(
                    target=self._receiver_loop, daemon=True
                )
                self._recv_thread.start()
                return True

            except (FileNotFoundError, ConnectionRefusedError, OSError):
                time.sleep(0.5)
            except Exception as e:
                print(f"[USBRelayManager] Socket connection error: {e}")
                time.sleep(0.5)

        return False

    def _receiver_loop(self):
        """
        Background thread that continuously receives messages from the server.
        Handles status pushes and ACKs. Auto-reconnects on connection loss.
        """
        recv_buffer = ""
        while self._recv_running:
            try:
                with self._socket_lock:
                    sock = self._socket
                if sock is None:
                    break

                sock.settimeout(1.0)
                try:
                    data = sock.recv(4096)
                    if not data:
                        break  # Server closed connection
                    recv_buffer += data.decode("utf-8", errors="replace")

                    while "\n" in recv_buffer:
                        line, recv_buffer = recv_buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            self._handle_server_message(line)
                except socket.timeout:
                    continue

            except (ConnectionResetError, BrokenPipeError, OSError):
                break
            except Exception:
                break

        # Connection lost — close and mark offline
        with self._socket_lock:
            if self._socket is not None:
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None

        with self._hw_status_lock:
            self._hw_status = "OFFLINE"

        # Auto-reconnect (if not shutting down)
        if self._recv_running:
            print("[USBRelayManager] IPC connection lost. Reconnecting in 2s...")
            time.sleep(2.0)
            if self._recv_running:
                self._connect_socket()

    def _handle_server_message(self, raw_json):
        """Processes a JSON message received from the server."""
        try:
            msg = json.loads(raw_json)
        except json.JSONDecodeError:
            return

        if msg.get("type") == "status":
            with self._hw_status_lock:
                self._hw_status = msg.get("hw_status", "OFFLINE")
        # ACKs are received but not needed for flow control in the current design

    def _send_command(self, cmd_dict):
        """Sends a JSON command to the hardware worker server via socket."""
        with self._socket_lock:
            if self._socket is None:
                return False
            try:
                self._socket.sendall((json.dumps(cmd_dict) + "\n").encode("utf-8"))
                return True
            except (BrokenPipeError, ConnectionResetError, OSError):
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None
                return False

    # ==========================================
    # HARDWARE STATUS PROPERTY (Thread-Safe)
    # ==========================================

    @property
    def hw_status(self):
        """Returns the cached hardware status string ("ONLINE" or "OFFLINE")."""
        with self._hw_status_lock:
            return self._hw_status

    # ==========================================
    # PORT SCANNING (Linux)
    # ==========================================

    def scan_available_ports(self):
        """
        Scans for available serial ports using fast, non-blocking glob matching.
        Note: actual serial I/O is owned by hardware_worker.py, not this class.
        This method exists solely to populate the GUI port selection dropdown.
        """
        ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        return ports if ports else ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"]

    # ==========================================
    # CONNECTION MANAGEMENT (Socket IPC Mode)
    # ==========================================

    def connect_port(self, port_name):
        """
        Records the target port and signals the IPC server to reset state.
        Actual serial connection is managed by hardware_worker.py.
        """
        self.port_name    = port_name
        self.is_connected = True
        self.relay_states  = [False, False, False, False]
        self.last_cmd_time = [0.0, 0.0, 0.0, 0.0]

        self._send_command({
            "cmd":                   "connect",
            "on_delay":              self.on_delay,
            "off_delay":             self.off_delay,
            "boot_self_test":        self.boot_self_test,
            "hardware_coil_enabled": self.hardware_coil_enabled,
        })

        print(f"[USBRelayManager] IPC mode: target port set to {port_name}")
        return True, "Socket IPC Active"

    def disconnect(self):
        """Resets all triggers to OFF state and marks as disconnected."""
        self._send_command({"cmd": "disconnect"})
        self.is_connected  = False
        self.port_name     = None
        self.relay_states  = [False, False, False, False]
        self.last_cmd_time = [0.0, 0.0, 0.0, 0.0]
        print("[USBRelayManager] IPC disconnected. All relays set to OFF.")

    # ==========================================
    # RELAY STATE CONTROL (Producer Commands)
    # ==========================================

    def trigger_relay(self, camera_id, state, force=False):
        """
        Maps camera_id (0-3) to station_1 through station_4 and sends
        a trigger command to the hardware worker via socket.

        The background worker applies non-blocking On-Delay / Off-Delay
        timers before physically firing the RM04U serial command.

        force=True: bypasses the in-memory latch and delay timers (manual
        diagnostic button presses).
        """
        try:
            channel_index = int(camera_id) + 1
        except (ValueError, TypeError):
            return False, f"Invalid camera_id: {camera_id}"

        if not 1 <= channel_index <= 4:
            return False, f"Channel index out of range: {channel_index}"

        # In-memory state-change latch — eliminates redundant IPC sends
        if not force and self.relay_states[channel_index - 1] == state:
            return True, "No transition (Filtered)"

        # Per-channel cooldown guard — ONLY applied to rapid ON re-triggers (chatter
        # prevention). OFF (state=False) commands are ALWAYS passed through immediately
        # so that a zone-clear signal is never delayed or dropped, preventing relay latching.
        now = time.time()
        if not force and state and self.relay_states[channel_index - 1] != state:
            elapsed = now - self.last_cmd_time[channel_index - 1]
            if elapsed < 0.5:
                return True, f"Cooldown active ({int(elapsed * 1000)}ms < 500ms)"

        self.relay_states[channel_index - 1]  = state
        self.last_cmd_time[channel_index - 1] = now

        cmd = {
            "cmd":     "trigger",
            "station": channel_index,
            "state":   1 if state else 0,
        }
        if force:
            cmd["manual"] = True

        write_success = self._send_command(cmd)
        command_str   = f"{'N' if state else 'F'}{channel_index}"

        if write_success:
            print(f"[USBRelayManager] IPC TX: station_{channel_index}_trigger -> "
                  f"{'1' if state else '0'} ({command_str})")
            return True, f"IPC: {command_str} -> {'ON' if state else 'OFF'}"
        else:
            return False, "IPC send failed"

    # ==========================================
    # HARDWARE COIL CONTROL
    # ==========================================

    def set_hardware_coil_enabled(self, enabled):
        """Toggles software coil relay outputs via IPC."""
        self.hardware_coil_enabled = 1 if enabled else 0
        self._send_command({
            "cmd":                   "config",
            "hardware_coil_enabled": self.hardware_coil_enabled,
        })
        print(f"[USBRelayManager] Hardware coil output set to {self.hardware_coil_enabled}")

    # ==========================================
    # TIMER CONFIGURATION (On-Delay / Off-Delay)
    # ==========================================

    def update_delay_config(self, on_delay, off_delay):
        """Updates timer configuration and pushes new values to the hardware worker."""
        self.on_delay  = float(on_delay)
        self.off_delay = float(off_delay)
        self._send_command({
            "cmd":           "config",
            "on_delay":      self.on_delay,
            "off_delay":     self.off_delay,
            "boot_self_test": self.boot_self_test,
        })
        print(f"[USBRelayManager] Timer config: on_delay={self.on_delay}s, "
              f"off_delay={self.off_delay}s")

    def update_boot_self_test(self, enabled):
        """Updates the boot_self_test flag and pushes to the hardware worker."""
        self.boot_self_test = 1 if enabled else 0
        self._send_command({
            "cmd":            "config",
            "boot_self_test": self.boot_self_test,
        })
        print(f"[USBRelayManager] Boot self-test {'ENABLED' if enabled else 'DISABLED'}")

    # ==========================================
    # DYNAMIC RELAY MAPPING
    # ==========================================

    def update_relay_mapping(self, mapping_list, mapping_2=None, enable_1=None, enable_2=None):
        """
        Updates the station-to-relay mapping via socket.

        Args:
            mapping_list: list of ints [relay_for_st1, relay_for_st2,
                                        relay_for_st3, relay_for_st4]
            mapping_2: optional second relay mapping per station
            enable_1: optional boolean list for enabling relay 1
            enable_2: optional boolean list for enabling relay 2
        """
        if mapping_2 is None:
            mapping_2 = [None, None, None, None]
        if enable_1 is None:
            enable_1 = [True, True, True, True]
        if enable_2 is None:
            enable_2 = [False, False, False, False]

        self._send_command({
            "cmd":       "relay_mapping",
            "mapping":   [(int(m) if m is not None else None) for m in mapping_list],
            "mapping_2": [(int(m) if m is not None else None) for m in mapping_2],
            "enable_1":  [bool(m) for m in enable_1],
            "enable_2":  [bool(m) for m in enable_2],
        })
        print(f"[USBRelayManager] Relay mapping updated: st1={mapping_list[0]}/{mapping_2[0]}, st2={mapping_list[1]}/{mapping_2[1]}, st3={mapping_list[2]}/{mapping_2[2]}, st4={mapping_list[3]}/{mapping_2[3]}")

    # ==========================================
    # LIFECYCLE CLEANUP
    # ==========================================

    def cleanup(self):
        """Gracefully shuts down the socket connection and receiver thread."""
        self._recv_running = False
        with self._socket_lock:
            if self._socket is not None:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None
        print("[USBRelayManager] IPC cleanup complete.")
