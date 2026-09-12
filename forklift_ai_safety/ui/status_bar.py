from PyQt5.QtWidgets import QFrame, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import pyqtSignal

class StatusBar(QFrame):
    """
    HMI Global Alert Footer. Displays real-time centralized warning indicators 
    and handles application teardown.
    """
    exit_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusBarPanel")
        
        self.setStyleSheet("""
            QFrame#statusBarPanel {
                background-color: #151a22;
                border: 1px solid #232d38;
                border-radius: 6px;
            }
            QLabel#statusLabel {
                font-size: 13px;
                font-weight: 800;
                padding: 10px 16px;
                border-radius: 4px;
                letter-spacing: 0.5px;
            }
            QPushButton#btnExit {
                background-color: #4a1d1d;
                border: 1px solid #742a2a;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 11px;
                font-weight: 800;
                color: #feb2b2;
                text-transform: uppercase;
            }
            QPushButton#btnExit:hover {
                background-color: #742a2a;
                color: #ffffff;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(12)
        
        self.status_label = QLabel("✔ SYSTEM OPERATING NORMALLY - ALL SECTORS SECURE")
        self.status_label.setObjectName("statusLabel")
        self.set_state(False)  # Safe by default
        layout.addWidget(self.status_label, stretch=1)
        
        self.btn_exit = QPushButton("❌ SHUTDOWN SYS", objectName="btnExit")
        self.btn_exit.clicked.connect(self.exit_clicked.emit)
        layout.addWidget(self.btn_exit)

    def set_state(self, is_warning, message=None):
        """
        Switches the footer theme dynamically based on overall security state.
        """
        if is_warning:
            text = message if message else "⚠️ CRITICAL WARNING: ZONE VIOLATION DETECTED! INTERFACE E-STOP ACTIVE"
            self.status_label.setText(text)
            self.status_label.setStyleSheet("""
                background-color: #742a2a;
                color: #fff5f5;
                border: 1px solid #e53e3e;
            """)
        else:
            text = message if message else "✔ SYSTEM OPERATING NORMALLY - ALL SECTORS SECURE"
            self.status_label.setText(text)
            self.status_label.setStyleSheet("""
                background-color: #1c4527;
                color: #c6f6d5;
                border: 1px solid #2f855a;
            """)
