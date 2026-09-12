from PyQt5.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QComboBox
from PyQt5.QtCore import pyqtSignal, QRect, Qt
from PyQt5.QtGui import QPixmap
from ui.video_panel import VideoLabel

class CameraPanelWidget(QFrame):
    """
    Independent Camera Panel UI Component. Fully self-contained monitoring widget
    displaying live video, LED alarm state, object count, FPS, camera source selection,
    and enable/disable toggles.
    """
    roi_changed = pyqtSignal(int, QRect)
    source_changed = pyqtSignal(int, object)  # cam_id, new_source
    status_changed = pyqtSignal(int, bool)    # cam_id, is_enabled

    def __init__(self, cam_id, initial_source, parent=None):
        super().__init__(parent)
        self.cam_id = cam_id
        self.source = initial_source
        self.is_enabled = True
        
        self.setObjectName("cameraPanel")
        
        # Apply premium dark HMI SCADA aesthetics
        self.setStyleSheet("""
            QFrame#cameraPanel {
                background-color: #161b24;
                border: 2px solid #283344;
                border-radius: 8px;
            }
            QFrame#cameraPanel[warning="true"] {
                border: 2px solid #e53e3e;
                background-color: #1f181c;
            }
            QLabel#panelTitle {
                color: #e2e8f0;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.5px;
                text-transform: uppercase;
            }
            QLabel#metricText {
                color: #a0aec0;
                font-size: 10px;
                font-weight: 700;
            }
            QComboBox {
                background-color: #202734;
                border: 1px solid #303d52;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 10px;
                color: #ffffff;
                font-weight: 600;
            }
            QComboBox:hover {
                border: 1px solid #4a5c78;
            }
            QPushButton#btnToggle {
                background-color: #1a202c;
                color: #cbd5e0;
                font-size: 10px;
                font-weight: bold;
                border: 1px solid #4a5568;
                border-radius: 4px;
                padding: 5px 10px;
                text-transform: uppercase;
            }
            QPushButton#btnToggle:hover {
                background-color: #2d3748;
            }
            QPushButton#btnToggle[active="false"] {
                background-color: #2f855a;
                color: #e6fffa;
                border: 1px solid #276749;
            }
            QPushButton#btnToggle[active="false"]:hover {
                background-color: #38a169;
            }
        """)
        
        # Layout definition
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        
        # --- TITLE BAR CONTROLS ---
        title_bar = QHBoxLayout()
        self.title_label = QLabel(f"🚚 STATION {self.cam_id + 1:02d} - ACTIVE")
        self.title_label.setObjectName("panelTitle")
        title_bar.addWidget(self.title_label)
        
        title_bar.addStretch()
        
        # LED circle alarm beacon
        self.led_indicator = QLabel()
        self.led_indicator.setFixedSize(12, 12)
        
        self.status_text_label = QLabel("SAFE")
        self.status_text_label.setStyleSheet("color: #34C759; font-size: 10px; font-weight: 800;")
        
        title_bar.addWidget(self.led_indicator)
        title_bar.addWidget(self.status_text_label)
        
        self.set_led_state(False) # Safe initially
        layout.addLayout(title_bar)
        
        # --- RENDERING SURFACE ---
        self.video_label = VideoLabel(self)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setScaledContents(True)
        self.video_label.setMinimumSize(320, 240)
        self.video_label.setStyleSheet("background-color: #06090e; border: 1px solid #1c2330; border-radius: 4px;")
        self.video_label.roi_updated.connect(self.on_roi_updated)
        
        layout.addWidget(self.video_label, stretch=1)
        
        # --- BOTTOM ACTION CONTROLS ---
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(6)
        
        # Source Dropdown Setup
        self.source_combo = QComboBox()
        self.source_combo.addItems([
            f"Simulated Feed {self.cam_id + 1}",
            "Webcam (Device 0)",
            "External Camera 1",
            "External Camera 2"
        ])
        # Mapping index to actual core parameters
        self.source_map = {
            0: f"Simulated_{self.cam_id}",
            1: 0,
            2: 1,
            3: 2
        }
        self.source_combo.currentIndexChanged.connect(self.on_source_changed)
        bottom_bar.addWidget(self.source_combo, stretch=2)
        
        # Performance Indicators
        self.metrics_label = QLabel("OBJ: 0 | FPS: 0.0")
        self.metrics_label.setObjectName("metricText")
        bottom_bar.addWidget(self.metrics_label, stretch=2)
        
        # Status Toggles
        self.toggle_button = QPushButton("DEACTIVATE")
        self.toggle_button.setObjectName("btnToggle")
        self.toggle_button.setProperty("active", "true")
        self.toggle_button.clicked.connect(self.on_toggle_clicked)
        bottom_bar.addWidget(self.toggle_button, stretch=1)
        
        layout.addLayout(bottom_bar)

    def set_led_state(self, is_breached):
        if is_breached:
            # High-intensity red beacon
            self.led_indicator.setStyleSheet("background-color: #e53e3e; border-radius: 6px; border: 1px solid #9b2c2c;")
            self.status_text_label.setText("BREACH")
            self.status_text_label.setStyleSheet("color: #e53e3e; font-size: 10px; font-weight: 800;")
            self.setProperty("warning", "true")
        else:
            # Solid green safety beacon
            self.led_indicator.setStyleSheet("background-color: #38a169; border-radius: 6px; border: 1px solid #22543d;")
            self.status_text_label.setText("SAFE")
            self.status_text_label.setStyleSheet("color: #38a169; font-size: 10px; font-weight: 800;")
            self.setProperty("warning", "false")
        
        # Polish HMI dynamic background states
        self.style().unpolish(self)
        self.style().polish(self)

    def on_roi_updated(self, qrect):
        self.roi_changed.emit(self.cam_id, qrect)

    def on_source_changed(self, index):
        real_source = self.source_map.get(index, f"Simulated_{self.cam_id}")
        self.source = real_source
        self.source_changed.emit(self.cam_id, real_source)

    def on_toggle_clicked(self):
        self.is_enabled = not self.is_enabled
        if self.is_enabled:
            self.toggle_button.setText("DEACTIVATE")
            self.toggle_button.setProperty("active", "true")
            self.title_label.setText(f"🚚 STATION {self.cam_id + 1:02d} - ACTIVE")
        else:
            self.toggle_button.setText("ACTIVATE")
            self.toggle_button.setProperty("active", "false")
            self.title_label.setText(f"🚚 STATION {self.cam_id + 1:02d} - STANDBY")
            self.set_led_state(False) # Clear alarm if disabled
            
        self.toggle_button.style().unpolish(self.toggle_button)
        self.toggle_button.style().polish(self.toggle_button)
        
        self.status_changed.emit(self.cam_id, self.is_enabled)

    def update_panel_data(self, qimage, objects_count, warning, fps):
        if not self.is_enabled:
            self.metrics_label.setText("MONITOR OFFLINE")
            self.video_label.setPixmap(QPixmap.fromImage(qimage))
            return
            
        # Draw frame buffer on VideoLabel
        self.video_label.setPixmap(QPixmap.fromImage(qimage))
        # Match alerts status LED
        self.set_led_state(warning)
        # Update FPS metrics
        self.metrics_label.setText(f"OBJ: {objects_count} | FPS: {fps:.1f}")
