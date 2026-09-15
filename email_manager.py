import os
import json
import time
import smtplib
from email.message import EmailMessage
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict

from PyQt5.QtCore import QThread, pyqtSignal

@dataclass
class EmailConfig:
    enabled: bool = False
    smtp_server: str = ""
    smtp_port: int = 587
    smtp_tls: str = "STARTTLS" # "STARTTLS", "SSL", or "NONE"
    sender_email: str = ""
    sender_password: str = ""
    recipients: List[str] = field(default_factory=list)
    subject_template: str = "Forklift Safety Report - {machine} - {timestamp}"
    interval_hours: float = 24.0
    max_retries: int = 3
    event_triggers: Dict[str, bool] = field(default_factory=lambda: {
        "alarm": False,
        "camera_offline": False,
        "hardware_offline": False,
        "relay_failure": False,
        "app_restart": False,
        "unhandled_exception": False
    })

class EmailQueue:
    """Persistent queue for failed emails to allow retries."""
    def __init__(self, queue_file="email_queue.json"):
        self.queue_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), queue_file)
        self._items = self._load()

    def _load(self):
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save(self):
        try:
            with open(self.queue_file, 'w') as f:
                json.dump(self._items, f, indent=4)
        except Exception as e:
            print(f"Error saving email queue: {e}")

    def enqueue(self, item):
        item['attempts'] = item.get('attempts', 0)
        self._items.append(item)
        self._save()

    def dequeue(self):
        if not self._items:
            return None
        item = self._items.pop(0)
        self._save()
        return item
        
    def peek_all(self):
        return list(self._items)


class EmailWorker(QThread):
    """
    Background worker for sending emails and creating reports.
    Does not block the GUI.
    """
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, config: EmailConfig, gui_ref, is_test=False, event_name=None, pre_captured_screenshots=None):
        super().__init__()
        self.config = config
        self.gui_ref = gui_ref
        self.is_test = is_test
        self.event_name = event_name
        self.pre_captured_screenshots = pre_captured_screenshots or []
        self.queue = EmailQueue()
        self.history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_history.json")

    def log_history(self, status, error_msg, duration, attachment_name):
        history = []
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    history = json.load(f)
            except Exception as e:
                print(f"Failed to read history: {e}")
                
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "recipients": self.config.recipients,
            "status": status,
            "duration": f"{duration:.2f}s",
            "error_message": error_msg,
            "attachment_name": attachment_name
        }
        history.append(entry)
        
        # Keep last 100 entries
        if len(history) > 100:
            history = history[-100:]
            
        try:
            with open(self.history_file, 'w') as f:
                json.dump(history, f, indent=4)
        except Exception as e:
            print(f"Failed to write history: {e}")

    def run(self):
        start_time = time.time()
        attachment_name = "None"
        try:
            self.progress.emit("Preparing report data...")
            import platform
            machine = platform.node()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            subject = self.config.subject_template.replace("{machine}", machine).replace("{timestamp}", timestamp)
            
            if self.is_test:
                subject = f"[TEST] {subject}"
                body = "This is a test email from the AI Forklift Safety System.\n\nEverything is configured correctly."
                zip_path = None
            else:
                if self.event_name:
                    subject = f"[EVENT: {self.event_name.upper()}] {subject}"
                    
                # We need to import ReportManager locally to avoid circular dependencies if any
                from report_manager import ReportManager
                rm = ReportManager()
                
                # Fetch settings
                global_config = getattr(self.gui_ref, "global_settings", {}) if self.gui_ref else {}
                # The config should be updated in ai_gui_system, but if we're passing it directly:
                # Actually ai_gui_system config.json has report_settings
                report_settings = {}
                try:
                    with open("config.json", "r") as f:
                        full_config = json.load(f)
                        report_settings = full_config.get("report_settings", {})
                except Exception as e:
                    print(f"Failed to read config for reports: {e}")
                
                include_txt = report_settings.get("include_txt", True)
                include_pdf = report_settings.get("include_pdf", True)
                
                self.progress.emit("Generating reports...")
                txt_path = rm.generate_txt_report(self.gui_ref) if include_txt else None
                pdf_path = rm.generate_pdf_report(self.gui_ref, self.pre_captured_screenshots) if include_pdf else None
                
                self.progress.emit("Compressing into ZIP...")
                zip_path = rm.build_zip_package(txt_path, pdf_path, self.pre_captured_screenshots)
                attachment_name = os.path.basename(zip_path)
                body = f"Attached is the automated system report generated at {timestamp} for {machine}.\n\n"
                
                if self.event_name:
                    body = f"An event triggered this report: {self.event_name}\n\n" + body

            # Create message
            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = self.config.sender_email
            msg['To'] = ", ".join(self.config.recipients)
            msg.set_content(body)

            if zip_path and os.path.exists(zip_path):
                with open(zip_path, 'rb') as f:
                    zip_data = f.read()
                msg.add_attachment(zip_data, maintype='application', subtype='zip', filename=attachment_name)

            self.progress.emit("Connecting to SMTP server...")
            
            # Send Email
            if self.config.smtp_tls == "SSL":
                server = smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port, timeout=30)
                if self.config.smtp_tls == "STARTTLS":
                    server.starttls()
            
            self.progress.emit("Authenticating...")
            if self.config.sender_password:
                server.login(self.config.sender_email, self.config.sender_password)
                
            self.progress.emit("Sending email...")
            server.send_message(msg)
            server.quit()

            duration = time.time() - start_time
            self.log_history("Success", "", duration, attachment_name)
            
            # Process Retry Queue if any
            self.process_queue()
            
            self.finished.emit(True, "Email sent successfully.")

        except Exception as e:
            error_msg = str(e)
            duration = time.time() - start_time
            self.log_history("Failed", error_msg, duration, attachment_name)
            
            if not self.is_test:
                # Queue for retry
                self.queue.enqueue({
                    "config": self.config.__dict__,
                    "is_test": self.is_test,
                    "event_name": self.event_name,
                    "error": error_msg,
                    "timestamp": time.time()
                })
                self.finished.emit(False, f"Failed to send email. Queued for retry. Error: {error_msg}")
            else:
                self.finished.emit(False, f"Test email failed: {error_msg}")
                
    def process_queue(self):
        """Attempts to send items in the retry queue."""
        # Simple implementation: we pop the oldest, if it fails it goes back (with attempt++).
        # We only do one item to avoid stalling the thread forever if network is down.
        item = self.queue.dequeue()
        if not item:
            return
            
        attempts = item.get("attempts", 0) + 1
        if attempts > self.config.max_retries:
            self.progress.emit(f"Dropped queued email after {self.config.max_retries} failed attempts.")
            return
            
        try:
            self.progress.emit("Attempting to send queued email...")
            # We recreate a simple notification for the queued item
            # since generating the report again might be stale or unnecessary.
            # For this implementation, we'll just send a notification that an email failed.
            # A more robust system would save the ZIP and retry the exact ZIP.
            # To keep it production-grade but bounded in complexity, we'll notify of the past failure.
            msg = EmailMessage()
            msg['Subject'] = f"[RETRY {attempts}/{self.config.max_retries}] Forklift Safety System"
            msg['From'] = self.config.sender_email
            msg['To'] = ", ".join(self.config.recipients)
            msg.set_content(f"A previous email failed to send.\nOriginal Error: {item.get('error')}\nTime: {datetime.fromtimestamp(item.get('timestamp', 0))}")
            
            if self.config.smtp_tls == "SSL":
                server = smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port, timeout=30)
                if self.config.smtp_tls == "STARTTLS":
                    server.starttls()
            
            if self.config.sender_password:
                server.login(self.config.sender_email, self.config.sender_password)
            server.send_message(msg)
            server.quit()
            self.progress.emit("Successfully sent queued email.")
        except Exception as e:
            item['attempts'] = attempts
            item['error'] = str(e)
            self.queue.enqueue(item)
            self.progress.emit(f"Retry failed. Re-queued. Error: {e}")


class EmailScheduler(QThread):
    """
    Independent daemon thread that fires the scheduled email.
    """
    trigger_report_email = pyqtSignal()
    next_send_time_changed = pyqtSignal(str)

    def __init__(self, config=None, gui_ref=None):
        super().__init__()
        self.gui_ref = gui_ref
        self.running = False
        self.interval_hours = 24.0
        self.next_run = 0
        self.enabled = False
        self.load_config()

    def load_config(self):
        try:
            with open("config.json", "r") as f:
                data = json.load(f)
                email_settings = data.get("email_settings", {})
                self.enabled = email_settings.get("enabled", False)
                self.interval_hours = email_settings.get("interval_hours", 24.0)
        except Exception as e:
            print(f"Failed to load config in scheduler: {e}")

    def update_config(self):
        self.load_config()
        # Reset the timer immediately
        self.next_run = time.time() + (self.interval_hours * 3600)
        self.emit_next_time()

    def emit_next_time(self):
        if not self.enabled:
            self.next_send_time_changed.emit("Disabled")
            return
            
        remaining = max(0, self.next_run - time.time())
        if remaining == 0:
            self.next_send_time_changed.emit("Now")
        else:
            h = int(remaining // 3600)
            m = int((remaining % 3600) // 60)
            self.next_send_time_changed.emit(f"In {h}h {m}m")

    def run(self):
        self.running = True
        self.next_run = time.time() + (self.interval_hours * 3600)
        
        last_emit = 0
        
        while self.running:
            now = time.time()
            
            # Emit updates to GUI every minute
            if now - last_emit > 60:
                self.emit_next_time()
                last_emit = now
                
            if self.enabled and now >= self.next_run:
                self.trigger_report_email.emit()
                self.next_run = now + (self.interval_hours * 3600)
                self.emit_next_time()
                
            time.sleep(1)

    def stop(self):
        self.running = False
        self.wait(2000)
