from PyQt5.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QComboBox, QGridLayout, QListWidget, QListWidgetItem
from PyQt5.QtGui import QColor
from PyQt5.QtCore import pyqtSignal, Qt
import time

class SidebarPanel(QFrame):
    """
    HMI SCADA Global Control Sidebar.
    Encapsulates role management combos, global enable/disable triggers,
    and a live-scrolling terminal for alarm and user audit logging.
    """
    role_changed = pyqtSignal(str)
    enable_all = pyqtSignal()
    disable_all = pyqtSignal()
    adjust_roi = pyqtSignal()
    config_triggered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarPanel")
        
        self.setStyleSheet("""
            QFrame#sidebarPanel {
                background-color: #151a22;
                border-radius: 6px;
                border: 1px solid #232d38;
            }
            QLabel#sidebarTitle {
                font-size: 10px;
                font-weight: 800;
                color: #718096;
                text-transform: uppercase;
                letter-spacing: 0.75px;
            }
            QComboBox {
                background-color: #202734;
                border: 1px solid #303d52;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                color: #ffffff;
                font-weight: 700;
            }
            QComboBox:hover {
                border: 1px solid #4a5c78;
            }
            QPushButton {
                background-color: #222d3b;
                border: 1px solid #324256;
                border-radius: 4px;
                padding: 8px 4px;
                font-size: 11px;
                font-weight: 800;
                color: #e2e8f0;
                text-transform: uppercase;
            }
            QPushButton:hover {
                background-color: #2c3a4d;
            }
            QPushButton#btnStartAll {
                background-color: #153e21;
                border: 1px solid #22543d;
                color: #48bb78;
            }
            QPushButton#btnStartAll:hover {
                background-color: #1c512c;
            }
            QPushButton#btnStopAll {
                background-color: #5c2d1d;
                border: 1px solid #742a2a;
                color: #f6ad55;
            }
            QPushButton#btnStopAll:hover {
                background-color: #6b3522;
            }
            QPushButton#btnAdjustRoi {
                background-color: #1a365d;
                border: 1px solid #2b6cb0;
                color: #63b3ed;
            }
            QPushButton#btnAdjustRoi:hover {
                background-color: #2b548a;
            }
            QListWidget {
                background-color: #090c10;
                border: 1px solid #1a222d;
                border-radius: 4px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10px;
                color: #cbd5e0;
                padding: 4px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # --- ACCESS LEVEL SELECTOR ---
        layout.addWidget(QLabel("🔒 SECURITY ACCESS LEVEL", objectName="sidebarTitle"))
        self.role_combo = QComboBox()
        self.role_combo.addItems(["Operator", "Supervisor", "Engineer"])
        self.role_combo.currentTextChanged.connect(self.on_role_changed)
        layout.addWidget(self.role_combo)
        
        layout.addSpacing(4)
        
        # --- SYSTEM GLOBAL CONTROLS ---
        layout.addWidget(QLabel("📊 SCADA CONSOLE OVERRIDES", objectName="sidebarTitle"))
        
        grid_layout = QGridLayout()
        grid_layout.setSpacing(6)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_start = QPushButton("▶ ENABLE ALL", objectName="btnStartAll")
        self.btn_start.clicked.connect(self.enable_all.emit)
        grid_layout.addWidget(self.btn_start, 0, 0)
        
        self.btn_stop = QPushButton("■ DISABLE ALL", objectName="btnStopAll")
        self.btn_stop.clicked.connect(self.disable_all.emit)
        grid_layout.addWidget(self.btn_stop, 0, 1)
        
        self.btn_draw = QPushButton("✏ ADJUST ROI", objectName="btnAdjustRoi")
        self.btn_draw.clicked.connect(self.adjust_roi.emit)
        self.btn_draw.setEnabled(False) # Default locked by Operator role
        grid_layout.addWidget(self.btn_draw, 1, 0)
        
        self.btn_config = QPushButton("⚙ CONFIGURATION")
        self.btn_config.clicked.connect(self.config_triggered.emit)
        grid_layout.addWidget(self.btn_config, 1, 1)
        
        layout.addLayout(grid_layout)
        
        layout.addSpacing(4)
        
        # --- INDUSTRIAL HMI LOGS TERMINAL ---
        layout.addWidget(QLabel("📜 LIVE SCADA EVENTS AUDIT", objectName="sidebarTitle"))
        
        self.log_widget = QListWidget()
        layout.addWidget(self.log_widget, stretch=1)
        
        # Default logs
        self.add_log("System Kernel initialized successfully.")
        self.add_log("Security level: OPERATOR engaged.")

    def on_role_changed(self, role):
        self.role_changed.emit(role)

    def set_role_combobox_silent(self, role):
        self.role_combo.blockSignals(True)
        self.role_combo.setCurrentText(role)
        self.role_combo.blockSignals(False)

    def enable_roi_button(self, enabled):
        self.btn_draw.setEnabled(enabled)

    def add_log(self, text, type="info"):
        """
        Appends a formatted, color-coded entry into the scrolling terminal feed.
        """
        timestamp = time.strftime("%H:%M:%S")
        log_item = QListWidgetItem(f"[{timestamp}] {text}")
        
        if type == "warning":
            log_item.setForeground(QColor("#fc8181")) # soft bright red
        elif type == "success":
            log_item.setForeground(QColor("#68d391")) # soft bright green
        elif type == "config":
            log_item.setForeground(QColor("#63b3ed")) # cyan highlight
        else:
            log_item.setForeground(QColor("#a0aec0")) # charcoal silver
            
        self.log_widget.addItem(log_item)
        self.log_widget.scrollToBottom()
        
        # Cap events count in GUI buffer
        if self.log_widget.count() > 80:
            self.log_widget.takeItem(0)
