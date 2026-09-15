import os
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QCheckBox, QComboBox, QLineEdit,
    QTextEdit, QSpinBox, QDoubleSpinBox, QScrollArea, QListWidget,
    QMessageBox
)
from PyQt5.QtCore import Qt

from email_manager import EmailConfig, EmailWorker
from storage_manager import StorageWorker


class ReportsEmailPage(QWidget):
    """
    Independent GUI page for configuring and triggering reports, emails, and storage cleanup.
    Matches the industrial SCADA theme.
    """
    def __init__(self, gui_ref, report_manager, email_scheduler):
        super().__init__()
        self.gui_ref = gui_ref
        self.report_manager = report_manager
        self.email_scheduler = email_scheduler
        self.config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        self.history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_history.json")
        
        # Load initial config
        self.config = self._load_config()
        self.email_config = self.config.get("email_settings", {})
        self.report_config = self.config.get("report_settings", {})
        self.storage_config = self.config.get("storage_settings", {})

        self.init_ui()
        self.update_history_log()
        
        # Connect to scheduler signal
        self.email_scheduler.next_send_time_changed.connect(self.update_next_send_label)

    def _load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Failed to read config: {e}")
        return {}

    def _save_config(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def init_ui(self):
        self.setStyleSheet("""
            QGroupBox {
                border: 2px solid #2d3846; border-radius: 6px; margin-top: 10px;
                font-family: 'Segoe UI Semibold'; font-size: 12px; font-weight: bold; color: #63b3ed;
                background-color: #16161a;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; background-color: #16161a;}
            QLabel { color: #e2e8f0; font-family: 'Segoe UI Semibold'; font-size: 11px; }
            QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background-color: #1d212a; color: #ffffff; padding: 6px; border: 1px solid #2d3846; border-radius: 4px;
            }
            QPushButton {
                background-color: #212630; border: 1px solid #2d3846; color: #cbd5e0;
                font-family: 'Segoe UI Semibold'; font-size: 11px; font-weight: bold; border-radius: 4px; padding: 8px 16px;
            }
            QPushButton:hover { background-color: #2d3545; }
            QPushButton.primary {
                background-color: #1a365d; border: 1px solid #2b6cb0; color: #ffffff;
            }
            QPushButton.primary:hover { background-color: #2b548a; }
            QPushButton.danger {
                background-color: #742a2a; border: 1px solid #c53030; color: #ffffff;
            }
            QPushButton.danger:hover { background-color: #9b2c2c; }
            QCheckBox { color: #e2e8f0; font-family: 'Segoe UI Semibold'; font-size: 11px; }
        """)

        main_layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")
        content_layout = QVBoxLayout(scroll_content)

        # ------------------------------------------------------------
        # EMAIL CONFIGURATION
        # ------------------------------------------------------------
        group_email = QGroupBox("📧 EMAIL CONFIGURATION")
        email_layout = QGridLayout(group_email)
        
        self.chk_enable_email = QCheckBox("Enable Automatic Scheduled Email")
        self.chk_enable_email.setChecked(self.email_config.get("enabled", False))
        email_layout.addWidget(self.chk_enable_email, 0, 0, 1, 2)
        
        email_layout.addWidget(QLabel("SMTP Server:"), 1, 0)
        self.inp_smtp_server = QLineEdit(self.email_config.get("smtp_server", ""))
        email_layout.addWidget(self.inp_smtp_server, 1, 1)
        
        email_layout.addWidget(QLabel("SMTP Port:"), 1, 2)
        self.inp_smtp_port = QSpinBox()
        self.inp_smtp_port.setRange(1, 65535)
        self.inp_smtp_port.setValue(self.email_config.get("smtp_port", 587))
        email_layout.addWidget(self.inp_smtp_port, 1, 3)
        
        email_layout.addWidget(QLabel("Security (TLS/SSL):"), 2, 0)
        self.cmb_tls = QComboBox()
        self.cmb_tls.addItems(["STARTTLS", "SSL", "NONE"])
        self.cmb_tls.setCurrentText(self.email_config.get("smtp_tls", "STARTTLS"))
        email_layout.addWidget(self.cmb_tls, 2, 1)
        
        email_layout.addWidget(QLabel("Sender Email:"), 3, 0)
        self.inp_sender = QLineEdit(self.email_config.get("sender_email", ""))
        email_layout.addWidget(self.inp_sender, 3, 1)
        
        email_layout.addWidget(QLabel("App Password:"), 3, 2)
        self.inp_password = QLineEdit(self.email_config.get("sender_password", ""))
        self.inp_password.setEchoMode(QLineEdit.Password)
        email_layout.addWidget(self.inp_password, 3, 3)
        
        email_layout.addWidget(QLabel("Recipients (one per line):"), 4, 0)
        self.inp_recipients = QTextEdit()
        self.inp_recipients.setFixedHeight(60)
        recipients = self.email_config.get("recipients", [])
        self.inp_recipients.setPlainText("\n".join(recipients))
        email_layout.addWidget(self.inp_recipients, 4, 1, 1, 3)
        
        email_layout.addWidget(QLabel("Interval (Hours):"), 5, 0)
        self.inp_interval = QDoubleSpinBox()
        self.inp_interval.setRange(0.1, 720.0)
        self.inp_interval.setValue(self.email_config.get("interval_hours", 24.0))
        email_layout.addWidget(self.inp_interval, 5, 1)

        btn_test_email = QPushButton("✉ Test Email")
        btn_test_email.clicked.connect(self.test_email)
        email_layout.addWidget(btn_test_email, 6, 2)
        
        btn_save_email = QPushButton("💾 Save Configuration")
        btn_save_email.setProperty("class", "primary")
        btn_save_email.clicked.connect(self.save_configuration)
        email_layout.addWidget(btn_save_email, 6, 3)

        content_layout.addWidget(group_email)

        # ------------------------------------------------------------
        # REPORT CONFIGURATION
        # ------------------------------------------------------------
        group_report = QGroupBox("📄 REPORT GENERATION")
        report_layout = QGridLayout(group_report)
        
        self.chk_txt = QCheckBox("Include TXT Report")
        self.chk_txt.setChecked(self.report_config.get("include_txt", True))
        report_layout.addWidget(self.chk_txt, 0, 0)
        
        self.chk_pdf = QCheckBox("Include PDF Report")
        self.chk_pdf.setChecked(self.report_config.get("include_pdf", True))
        report_layout.addWidget(self.chk_pdf, 0, 1)
        
        report_layout.addWidget(QLabel("Include Screenshots:"), 1, 0, 1, 2)
        
        ss_config = self.report_config.get("screenshots", {})
        self.chk_ss_dash = QCheckBox("Dashboard")
        self.chk_ss_dash.setChecked(ss_config.get("dashboard", True))
        report_layout.addWidget(self.chk_ss_dash, 2, 0)
        
        self.chk_ss_cam = QCheckBox("Camera Overview")
        self.chk_ss_cam.setChecked(ss_config.get("camera_overview", False))
        report_layout.addWidget(self.chk_ss_cam, 2, 1)
        
        self.chk_ss_hw = QCheckBox("Hardware Status")
        self.chk_ss_hw.setChecked(ss_config.get("hardware_status", False))
        report_layout.addWidget(self.chk_ss_hw, 3, 0)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_gen_txt = QPushButton("Generate TXT Now")
        btn_gen_txt.clicked.connect(self.generate_txt_now)
        btn_layout.addWidget(btn_gen_txt)
        
        btn_gen_pdf = QPushButton("Generate PDF Now")
        btn_gen_pdf.clicked.connect(self.generate_pdf_now)
        btn_layout.addWidget(btn_gen_pdf)
        
        btn_send_now = QPushButton("🚀 Send Scheduled Report NOW")
        btn_send_now.setProperty("class", "primary")
        btn_send_now.clicked.connect(self.send_scheduled_email)
        btn_layout.addWidget(btn_send_now)
        
        report_layout.addLayout(btn_layout, 4, 0, 1, 4)
        content_layout.addWidget(group_report)

        # ------------------------------------------------------------
        # STORAGE MANAGEMENT
        # ------------------------------------------------------------
        group_storage = QGroupBox("💾 STORAGE MANAGEMENT")
        storage_layout = QGridLayout(group_storage)
        
        self.chk_auto_cleanup = QCheckBox("Enable Automatic Cleanup")
        self.chk_auto_cleanup.setChecked(self.storage_config.get("auto_cleanup_enabled", False))
        storage_layout.addWidget(self.chk_auto_cleanup, 0, 0, 1, 2)
        
        storage_layout.addWidget(QLabel("Retention Days:"), 1, 0)
        self.inp_retention = QSpinBox()
        self.inp_retention.setRange(1, 3650)
        self.inp_retention.setValue(self.storage_config.get("retention_days", 30))
        storage_layout.addWidget(self.inp_retention, 1, 1)
        
        storage_layout.addWidget(QLabel("Max Folder Size (MB):"), 1, 2)
        self.inp_max_size = QSpinBox()
        self.inp_max_size.setRange(0, 100000)
        self.inp_max_size.setValue(self.storage_config.get("max_reports_mb", 500))
        self.inp_max_size.setToolTip("Set to 0 for unlimited")
        storage_layout.addWidget(self.inp_max_size, 1, 3)
        
        self.chk_archive = QCheckBox("Archive Mode (Move & Compress instead of Delete)")
        self.chk_archive.setChecked(self.storage_config.get("archive_mode", False))
        storage_layout.addWidget(self.chk_archive, 2, 0, 1, 2)
        
        btn_clean_now = QPushButton("🧹 Run Cleanup NOW")
        btn_clean_now.setProperty("class", "danger")
        btn_clean_now.clicked.connect(self.run_cleanup_now)
        storage_layout.addWidget(btn_clean_now, 2, 3)
        
        content_layout.addWidget(group_storage)

        # ------------------------------------------------------------
        # HISTORY & STATUS
        # ------------------------------------------------------------
        group_history = QGroupBox("⏱ STATUS & HISTORY")
        history_layout = QGridLayout(group_history)
        
        self.lbl_next_send = QLabel("Next Send: Calculating...")
        self.lbl_next_send.setStyleSheet("color: #48bb78; font-size: 13px; font-weight: bold;")
        history_layout.addWidget(self.lbl_next_send, 0, 0)
        
        self.lbl_status = QLabel("Ready.")
        history_layout.addWidget(self.lbl_status, 0, 1, 1, 3)
        
        self.list_history = QListWidget()
        self.list_history.setFixedHeight(120)
        self.list_history.setStyleSheet("""
            QListWidget { background-color: #111318; border: 1px solid #2d3846; color: #a0aec0; font-family: monospace; font-size: 11px;}
        """)
        history_layout.addWidget(self.list_history, 1, 0, 1, 4)
        
        btn_refresh_log = QPushButton("↻ Refresh Log")
        btn_refresh_log.clicked.connect(self.update_history_log)
        history_layout.addWidget(btn_refresh_log, 2, 3)

        content_layout.addWidget(group_history)
        
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

    def _get_email_config_from_ui(self) -> EmailConfig:
        recipients = [r.strip() for r in self.inp_recipients.toPlainText().split('\n') if r.strip()]
        cfg = EmailConfig(
            enabled=self.chk_enable_email.isChecked(),
            smtp_server=self.inp_smtp_server.text(),
            smtp_port=self.inp_smtp_port.value(),
            smtp_tls=self.cmb_tls.currentText(),
            sender_email=self.inp_sender.text(),
            sender_password=self.inp_password.text(),
            recipients=recipients,
            interval_hours=self.inp_interval.value()
        )
        return cfg

    def save_configuration(self):
        # Read from UI
        self.email_config["enabled"] = self.chk_enable_email.isChecked()
        self.email_config["smtp_server"] = self.inp_smtp_server.text()
        self.email_config["smtp_port"] = self.inp_smtp_port.value()
        self.email_config["smtp_tls"] = self.cmb_tls.currentText()
        self.email_config["sender_email"] = self.inp_sender.text()
        self.email_config["sender_password"] = self.inp_password.text()
        self.email_config["recipients"] = [r.strip() for r in self.inp_recipients.toPlainText().split('\n') if r.strip()]
        self.email_config["interval_hours"] = self.inp_interval.value()
        
        self.report_config["include_txt"] = self.chk_txt.isChecked()
        self.report_config["include_pdf"] = self.chk_pdf.isChecked()
        ss_config = self.report_config.setdefault("screenshots", {})
        ss_config["dashboard"] = self.chk_ss_dash.isChecked()
        ss_config["camera_overview"] = self.chk_ss_cam.isChecked()
        ss_config["hardware_status"] = self.chk_ss_hw.isChecked()
        
        self.storage_config["auto_cleanup_enabled"] = self.chk_auto_cleanup.isChecked()
        self.storage_config["retention_days"] = self.inp_retention.value()
        self.storage_config["max_reports_mb"] = self.inp_max_size.value()
        self.storage_config["archive_mode"] = self.chk_archive.isChecked()

        self.config["email_settings"] = self.email_config
        self.config["report_settings"] = self.report_config
        self.config["storage_settings"] = self.storage_config
        
        self._save_config()
        self.email_scheduler.update_config()
        
        if self.gui_ref:
            self.gui_ref.add_audit_log("Reports & Email configurations saved.", "config")
        QMessageBox.information(self, "Success", "Configuration saved successfully!")

    def update_next_send_label(self, text):
        self.lbl_next_send.setText(f"Next Send: {text}")

    def update_history_log(self):
        self.list_history.clear()
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    history = json.load(f)
                    # Show last 50, reversed
                    for entry in reversed(history[-50:]):
                        ts = entry.get('timestamp', 'Unknown')
                        status = entry.get('status', 'Unknown')
                        msg = entry.get('error_message', '')
                        dur = entry.get('duration', '')
                        text = f"[{ts}] {status.upper()} - {dur}"
                        if msg:
                            text += f" (Err: {msg})"
                        self.list_history.addItem(text)
            except Exception as e:
                print(f"Failed to read history log: {e}")

    def _capture_requested_screenshots(self):
        """Must be called on main thread before starting worker."""
        if not self.gui_ref:
            return []
            
        ss_config = self.report_config.get("screenshots", {})
        paths = []
        
        # Dashboard is stacked widget index 0 (Live View)
        if ss_config.get("dashboard", False):
            # Temporarily switch if needed, but grab() captures current state.
            # Best to just grab the main container
            if hasattr(self.gui_ref, "main_container"):
                p = self.report_manager.capture_screenshot(self.gui_ref.main_container, "dashboard")
                if p: paths.append(p)
                
        # To avoid UI flicker, we just capture what is currently visible or specifically requested elements.
        # Capturing specific hidden pages requires rendering them, which can glitch the UI.
        # In a production SCADA system, we only capture the main application window or active view.
        return paths

    def test_email(self):
        cfg = self._get_email_config_from_ui()
        if not cfg.smtp_server or not cfg.sender_email or not cfg.recipients:
            QMessageBox.warning(self, "Incomplete Configuration", "Please fill in Server, Sender, and at least one Recipient.")
            return
            
        self.lbl_status.setText("Sending test email...")
        self.worker = EmailWorker(cfg, self.gui_ref, is_test=True)
        self.worker.progress.connect(self.on_worker_progress)
        self.worker.finished.connect(self.on_email_finished)
        self.worker.start()

    def generate_txt_now(self):
        self.lbl_status.setText("Generating TXT...")
        try:
            path = self.report_manager.generate_txt_report(self.gui_ref)
            self.lbl_status.setText(f"TXT created: {path}")
            if self.gui_ref:
                self.gui_ref.add_audit_log(f"TXT Report generated: {path}", "success")
            QMessageBox.information(self, "Success", f"TXT Report generated at:\n{path}")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.lbl_status.setText("Failed to generate TXT.")
            if self.gui_ref:
                self.gui_ref.add_audit_log(f"Failed to generate TXT: {e}\n{tb}", "warning")
            QMessageBox.critical(self, "Error", f"Failed to generate TXT:\n{e}\n\n{tb}")

    def generate_pdf_now(self):
        self.lbl_status.setText("Generating PDF...")
        try:
            screenshots = self._capture_requested_screenshots()
            path = self.report_manager.generate_pdf_report(self.gui_ref, screenshots)
            self.lbl_status.setText(f"PDF created: {path}")
            if self.gui_ref:
                self.gui_ref.add_audit_log(f"PDF Report generated: {path}", "success")
            QMessageBox.information(self, "Success", f"PDF Report generated at:\n{path}")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.lbl_status.setText("Failed to generate PDF.")
            if self.gui_ref:
                self.gui_ref.add_audit_log(f"Failed to generate PDF: {e}\n{tb}", "warning")
            QMessageBox.critical(self, "Error", f"Failed to generate PDF:\n{e}\n\n{tb}")

    def send_scheduled_email(self):
        # This can be triggered by the scheduler or manual button
        cfg = self._get_email_config_from_ui()
        if not cfg.enabled and self.sender() != self:
            return # Don't auto-send if disabled
            
        if not cfg.smtp_server or not cfg.sender_email or not cfg.recipients:
            self.lbl_status.setText("Error: Email not configured.")
            return
            
        self.lbl_status.setText("Building and sending scheduled report...")
        screenshots = self._capture_requested_screenshots()
        
        self.worker = EmailWorker(cfg, self.gui_ref, is_test=False, pre_captured_screenshots=screenshots)
        self.worker.progress.connect(self.on_worker_progress)
        self.worker.finished.connect(self.on_email_finished)
        self.worker.start()

    def run_cleanup_now(self):
        self.lbl_status.setText("Running storage cleanup...")
        self.storage_worker = StorageWorker(self.config)
        self.storage_worker.progress.connect(self.on_worker_progress)
        self.storage_worker.finished.connect(self.on_cleanup_finished)
        self.storage_worker.start()

    def on_worker_progress(self, msg):
        self.lbl_status.setText(msg)

    def on_email_finished(self, success, msg):
        if success:
            self.lbl_status.setText(f"Success: {msg}")
            if self.gui_ref:
                self.gui_ref.add_audit_log("Email notification sent successfully.", "success")
        else:
            self.lbl_status.setText(f"Failed: {msg}")
            if self.gui_ref:
                self.gui_ref.add_audit_log(f"Email notification failed: {msg}", "warning")
        self.update_history_log()

    def on_cleanup_finished(self, success, msg):
        self.lbl_status.setText(msg)
        if self.gui_ref:
            if success:
                self.gui_ref.add_audit_log(f"Storage cleanup completed.", "success")
            else:
                self.gui_ref.add_audit_log(f"Storage cleanup error: {msg}", "warning")
