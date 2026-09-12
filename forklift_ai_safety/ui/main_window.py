import math
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QGridLayout, QInputDialog, QLineEdit, QMessageBox
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QImage

# Import UI components
from ui.camera_panel import CameraPanelWidget
from ui.sidebar_panel import SidebarPanel
from ui.status_bar import StatusBar

# Import Core sub-systems
from core.security import SecurityManager
from core.roi_manager import RoiManager
from core.camera_thread import CameraThread

NUM_STATIONS = 4  # Scalable grid size: support 1, 4, 8, 16 out of the box!

class MainWindow(QWidget):
    """
    Main SCADA Industrial Control HMI Dashboard.
    Manages dynamic camera layouts, coordinates background worker threads,
    verifies supervisor credentials, and outputs audit logs.
    """
    def __init__(self):
        super().__init__()
        
        # Initialize Core Logic Systems
        self.security = SecurityManager()
        self.roi_manager = RoiManager()
        
        # Window settings
        self.setWindowTitle("FORKLIFT AI SAFETY SYSTEM - CENTRAL OPERATIONS CONSOLE")
        self.setMinimumSize(1280, 800)
        self.current_role = "Operator"
        
        # Track warning states per station to manage audit logs (prevents spamming)
        self.warning_states = [False] * NUM_STATIONS
        
        # Base UI Styling
        self.setStyleSheet("""
            QWidget {
                background-color: #0b0f17;
                color: #e2e8f0;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
            }
            QFrame#mainContainer {
                background-color: #0f141c;
                border: 2px solid #1f2835;
                border-radius: 8px;
            }
        """)

        # Main Layout Setup
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        
        self.main_container = QFrame()
        self.main_container.setObjectName("mainContainer")
        outer_layout.addWidget(self.main_container)
        
        # Layout inside outer bezel shell
        container_layout = QVBoxLayout(self.main_container)
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(10)
        
        # --- HEADER BANNER ---
        header_layout = QHBoxLayout()
        self.header_title = QLabel("🚚 FORKLIFT AI SAFETY SYSTEMS - SCADA MASTER CONSOLE")
        self.header_title.setStyleSheet("""
            font-size: 16px;
            font-weight: 800;
            color: #ffffff;
            letter-spacing: 0.75px;
        """)
        header_layout.addWidget(self.header_title)
        header_layout.addStretch()
        
        self.integrity_label = QLabel("🛡️ SYSTEM INTEGRITY: SECURE")
        self.integrity_label.setStyleSheet("color: #48bb78; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        header_layout.addWidget(self.integrity_label)
        container_layout.addLayout(header_layout)
        
        # --- CENTRAL HMI CLIENTS & SIDEBAR ---
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(10)
        
        # 2x2 Scalable Grid Container
        self.grid_frame = QFrame()
        self.grid_frame.setStyleSheet("background: transparent; border: none;")
        self.grid_layout = QGridLayout(self.grid_frame)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(8)
        
        # Construct dynamic 1, 4, 8, 16 grid mathematically
        self.panels = []
        self.threads = []
        
        cols = int(math.ceil(math.sqrt(NUM_STATIONS)))
        
        for i in range(NUM_STATIONS):
            # Dynamic grid coords
            row = i // cols
            col = i % cols
            
            # Setup reusable CameraPanelWidget
            initial_source = f"Simulated_{i}"
            panel = CameraPanelWidget(cam_id=i, initial_source=initial_source)
            self.grid_layout.addWidget(panel, row, col)
            self.panels.append(panel)
            
            # Connect signals
            panel.roi_changed.connect(self.on_panel_roi_changed)
            panel.source_changed.connect(self.on_panel_source_changed)
            panel.status_changed.connect(self.on_panel_status_changed)
            
            # Setup background processing QThread
            thread = CameraThread(cam_id=i, source=initial_source)
            # Retrieve saved ROI boundary coordinates
            saved_roi = self.roi_manager.get_roi(i)
            thread.set_roi(saved_roi)
            panel.video_label.set_roi(saved_roi)
            
            thread.frame_processed.connect(self.on_thread_frame_processed)
            thread.camera_error.connect(self.on_thread_camera_error)
            
            self.threads.append(thread)
            
        middle_layout.addWidget(self.grid_frame, stretch=1)
        
        # Global Sidebar Controls Panel
        self.sidebar = SidebarPanel()
        self.sidebar.setFixedWidth(290)
        self.sidebar.role_changed.connect(self.on_role_changed)
        self.sidebar.enable_all.connect(self.on_global_enable_all)
        self.sidebar.disable_all.connect(self.on_global_disable_all)
        self.sidebar.adjust_roi.connect(self.on_global_adjust_roi)
        self.sidebar.config_triggered.connect(self.on_global_config_triggered)
        
        middle_layout.addWidget(self.sidebar)
        container_layout.addLayout(middle_layout)
        
        # --- FOOTER STATUS BANNER ---
        self.status_bar = StatusBar()
        self.status_bar.exit_clicked.connect(self.close_application)
        container_layout.addWidget(self.status_bar)
        
        # Start background camera threads
        for thread in self.threads:
            thread.start()

    # ==========================================
    # WORKER THREAD CALL EVENTS
    # ==========================================
    def on_thread_frame_processed(self, cam_id, qimage, objects_count, warning, fps):
        """
        Receives frame updates from the background threads and updates the correct UI grid channel.
        Also evaluates centralized alert logging when safety breaches occur.
        """
        if cam_id < len(self.panels):
            self.panels[cam_id].update_panel_data(qimage, objects_count, warning, fps)
            
        # Detect alarm trigger transition for live terminal event logging
        if warning != self.warning_states[cam_id]:
            self.warning_states[cam_id] = warning
            if warning:
                self.sidebar.add_log(f"ALERT: Danger zone BREACHED at Station {cam_id+1}!", "warning")
            else:
                self.sidebar.add_log(f"Station {cam_id+1}: Zone path cleared.", "success")
                
        # Calculate centralized warning states
        any_warning = any(self.warning_states)
        self.status_bar.set_state(any_warning)
        
        if any_warning:
            self.integrity_label.setText("⚠️ SYSTEM INTEGRITY: BREACH ACTIVE")
            self.integrity_label.setStyleSheet("color: #e53e3e; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        else:
            self.integrity_label.setText("🛡️ SYSTEM INTEGRITY: SECURE")
            self.integrity_label.setStyleSheet("color: #48bb78; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")

    def on_thread_camera_error(self, cam_id, err_msg):
        self.sidebar.add_log(f"ALERT: Station {cam_id+1} error - {err_msg}", "warning")

    # ==========================================
    # USER INTERACTIONS & PRIVILEGES
    # ==========================================
    def on_role_changed(self, role):
        """
        Handles access control. Demands passwords when upgrading privilege level.
        """
        if role == "Operator":
            self.current_role = "Operator"
            self.sidebar.enable_roi_button(False)
            for panel in self.panels:
                panel.video_label.set_editable(False)
            self.sidebar.add_log("Role: OPERATOR level engaged.")
            return

        # Request Authentication Password
        password, ok = QInputDialog.getText(
            self, "HMI Privilege Level Verification", f"Enter {role} Credentials Password:", QLineEdit.Password
        )
        if not ok:
            # Revert role combo selection quietly
            self.sidebar.set_role_combobox_silent(self.current_role)
            return

        if self.security.verify_password(role, password):
            self.current_role = role
            self.sidebar.enable_roi_button(True)
            for panel in self.panels:
                panel.video_label.set_editable(True)
            self.sidebar.add_log(f"Role: {role.upper()} access granted.", "success")
            QMessageBox.information(self, "Authorization Granted", f"Access Level Upgraded to {role}.")
        else:
            self.sidebar.set_role_combobox_silent(self.current_role)
            self.sidebar.add_log(f"AUDIT WARNING: Failed {role} login attempt!", "warning")
            QMessageBox.warning(self, "Authorization Denied", "Credentials verification failed.")

    # ==========================================
    # REUSED COMPONENT SIGNALS
    # ==========================================
    def on_panel_roi_changed(self, cam_id, qrect):
        """
        Triggered when ROI coordinates are drawn/adjusted. Automatically persists
        coordinates and configures the corresponding thread worker.
        """
        self.roi_manager.save_roi(cam_id, qrect)
        if cam_id < len(self.threads):
            self.threads[cam_id].set_roi(qrect)
        self.sidebar.add_log(f"Station {cam_id+1} ROI boundary saved successfully.", "config")

    def on_panel_source_changed(self, cam_id, source):
        if cam_id < len(self.threads):
            self.threads[cam_id].set_source(source)
        self.sidebar.add_log(f"Station {cam_id+1} source set to: {source}", "config")

    def on_panel_status_changed(self, cam_id, is_enabled):
        if cam_id < len(self.threads):
            self.threads[cam_id].set_enabled(is_enabled)
        state_str = "ENABLED" if is_enabled else "STANDBY"
        self.sidebar.add_log(f"Station {cam_id+1} monitoring set to {state_str}.", "config")

    # ==========================================
    # SIDEBAR PANEL ACTIONS
    # ==========================================
    def on_global_enable_all(self):
        self.sidebar.add_log("Global action: ACTIVATE ALL channels.", "config")
        for panel in self.panels:
            if not panel.is_enabled:
                panel.on_toggle_clicked()

    def on_global_disable_all(self):
        self.sidebar.add_log("Global action: DEACTIVATE ALL channels.", "config")
        for panel in self.panels:
            if panel.is_enabled:
                panel.on_toggle_clicked()

    def on_global_adjust_roi(self):
        self.sidebar.add_log("Global action: Drawing mode triggered for all channels.", "config")
        for panel in self.panels:
            panel.video_label.start_drawing_roi()

    def on_global_config_triggered(self):
        """
        Prompts role credential update in security profile, mimicking monolithic settings actions.
        """
        role, ok = QInputDialog.getItem(
            self, "SCADA Config Manager", "Select Target Role Profile:", ["Supervisor", "Engineer"], 0, False
        )
        if not ok: return

        current_password, ok = QInputDialog.getText(
            self, "Verify Credentials", f"Enter Current {role} Password:", QLineEdit.Password
        )
        if not ok or not self.security.verify_password(role, current_password):
            QMessageBox.warning(self, "Security Denied", "Profile verification failed.")
            return

        new_password, ok = QInputDialog.getText(
            self, "Configure Password", "Enter New Password:", QLineEdit.Password
        )
        if not ok: return

        confirm_password, ok = QInputDialog.getText(
            self, "Confirm Password", "Confirm New Password:", QLineEdit.Password
        )
        if not ok or new_password != confirm_password:
            QMessageBox.warning(self, "Security Failure", "Passwords mismatch error.")
            return

        self.security.change_password(role, new_password)
        self.sidebar.add_log(f"Security Profile: {role} credentials updated.", "success")
        QMessageBox.information(self, "Security Success", f"{role} credentials updated successfully.")

    # ==========================================
    # DE teardown routines
    # ==========================================
    def close_application(self):
        self.sidebar.add_log("SCADA Central Interface Shutdown requested.")
        for thread in self.threads:
            thread.stop()
        self.close()

    def closeEvent(self, event):
        # Guarantee background thread termination on close window
        for thread in self.threads:
            thread.stop()
        event.accept()
