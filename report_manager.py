import os
import time
import zipfile
from datetime import datetime
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPixmap

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    _HAS_REPORTLAB = True
except ImportError:
    _HAS_REPORTLAB = False


class ReportManager:
    """
    Independent Report Manager.
    Generates TXT and PDF reports without blocking the GUI.
    """
    def __init__(self):
        self.project_dir = os.path.dirname(os.path.abspath(__file__))
        self.reports_dir = os.path.join(self.project_dir, "Reports")
        self.screenshots_dir = os.path.join(self.reports_dir, "Screenshots")
        os.makedirs(self.reports_dir, exist_ok=True)
        os.makedirs(self.screenshots_dir, exist_ok=True)

    def _get_system_info(self, gui_ref):
        """Extracts necessary system info from the gui_ref safely."""
        import platform
        try:
            import psutil
            has_psutil = True
        except ImportError:
            has_psutil = False

        # Gather general info
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        machine_name = platform.node()
        os_name = platform.system() + " " + platform.release()
        
        # System Status
        current_user = getattr(gui_ref, "current_role", "Unknown")
        login_level = gui_ref.access_levels.get(current_user, 1) if hasattr(gui_ref, "access_levels") else 1
        uptime = getattr(gui_ref.metrics_engine._cache, "app_running_time_s", 0) if hasattr(gui_ref, "metrics_engine") else 0
        
        if uptime > 0:
            m, s = divmod(uptime, 60)
            h, m = divmod(m, 60)
            uptime_str = f"{int(h)}h {int(m)}m {int(s)}s"
        else:
            uptime_str = "Unknown"

        # Hardware/Health
        cpu_usage = psutil.cpu_percent() if has_psutil else "N/A"
        ram = psutil.virtual_memory() if has_psutil else None
        ram_usage = f"{ram.percent}%" if ram else "N/A"
        disk = psutil.disk_usage("/") if has_psutil else None
        disk_usage = f"{disk.percent}%" if disk else "N/A"
        
        # Hardware Status
        hw_status = "Unknown"
        if hasattr(gui_ref, "relay_manager"):
            hw_status = gui_ref.relay_manager.hw_status
            
        # Camera Info
        cameras = []
        if hasattr(gui_ref, "cards"):
            for i, card in enumerate(gui_ref.cards):
                cam_info = {
                    "id": i + 1,
                    "connected": card.camera_online,
                    "fps": getattr(card, "prev_time", 0), # Simplified FPS tracking for report
                    "active": card.is_active,
                    "warning": card.property("warning") == "true",
                    "objects": len(getattr(card, "last_persons", []))
                }
                cameras.append(cam_info)

        # Config Summary
        if hasattr(gui_ref, "global_settings"):
            on_delay = gui_ref.global_settings.get("on_delay", 0.0)
            off_delay = gui_ref.global_settings.get("off_delay", 1.5)
        else:
            on_delay = 0.0
            off_delay = 1.5
        
        # Recent Errors
        recent_errors = []
        if hasattr(gui_ref, "log_terminal"):
            count = gui_ref.log_terminal.count()
            # Get last 10 logs
            start_idx = max(0, count - 10)
            for i in range(start_idx, count):
                item = gui_ref.log_terminal.item(i)
                if item:
                    recent_errors.append(item.text())

        return {
            "timestamp": timestamp,
            "machine_name": machine_name,
            "os": os_name,
            "current_user": current_user,
            "login_level": login_level,
            "uptime": uptime_str,
            "cpu_usage": cpu_usage,
            "ram_usage": ram_usage,
            "disk_usage": disk_usage,
            "hw_status": hw_status,
            "cameras": cameras,
            "on_delay": on_delay,
            "off_delay": off_delay,
            "recent_errors": recent_errors
        }

    def generate_txt_report(self, gui_ref) -> str:
        """Generates a text report and returns the file path."""
        info = self._get_system_info(gui_ref)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"Report_{timestamp_str}.txt"
        filepath = os.path.join(self.reports_dir, filename)

        with open(filepath, 'w') as f:
            f.write(f"=== LIMITLESS FUTURE - AI FORKLIFT SAFETY SYSTEM REPORT ===\n")
            f.write(f"Timestamp: {info['timestamp']}\n")
            f.write(f"Machine Name: {info['machine_name']}\n")
            f.write(f"Operating System: {info['os']}\n")
            f.write("-" * 50 + "\n")
            f.write("SYSTEM STATUS\n")
            f.write(f"Current User: {info['current_user']} (Level {info['login_level']})\n")
            f.write(f"Uptime: {info['uptime']}\n")
            f.write("-" * 50 + "\n")
            f.write("CAMERA STATUS\n")
            for cam in info['cameras']:
                status = "Online" if cam['connected'] else "Offline"
                active = "Yes" if cam['active'] else "No"
                breach = "YES" if cam['warning'] else "NO"
                f.write(f"  Station {cam['id']}: {status} | Active: {active} | Objects: {cam['objects']} | Breach: {breach}\n")
            f.write("-" * 50 + "\n")
            f.write("HARDWARE & HEALTH\n")
            f.write(f"Relay Status: {info['hw_status']}\n")
            f.write(f"CPU Usage: {info['cpu_usage']}%\n")
            f.write(f"RAM Usage: {info['ram_usage']}\n")
            f.write(f"Disk Usage: {info['disk_usage']}\n")
            f.write("-" * 50 + "\n")
            f.write("CONFIGURATION SUMMARY\n")
            f.write(f"On-Delay: {info['on_delay']}s\n")
            f.write(f"Off-Delay: {info['off_delay']}s\n")
            f.write("-" * 50 + "\n")
            f.write("RECENT SYSTEM LOGS\n")
            for log in info['recent_errors']:
                f.write(f"  {log}\n")
            f.write("-" * 50 + "\n")
            f.write("END OF REPORT\n")

        return filepath

    def generate_pdf_report(self, gui_ref, screenshots=None) -> str:
        """Generates a PDF report and returns the file path. Fallback to TXT if reportlab not found."""
        if not _HAS_REPORTLAB:
            print("[ReportManager] reportlab not installed, falling back to TXT report.")
            return self.generate_txt_report(gui_ref)

        if screenshots is None:
            screenshots = []

        info = self._get_system_info(gui_ref)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"Report_{timestamp_str}.pdf"
        filepath = os.path.join(self.reports_dir, filename)

        doc = SimpleDocTemplate(filepath, pagesize=letter)
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=20,
            textColor='#1a365d'
        )
        h2_style = ParagraphStyle(
            'Heading2Style',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=10,
            spaceBefore=15,
            textColor='#2b6cb0'
        )
        body_style = styles['Normal']

        story = []
        
        # Title
        story.append(Paragraph("AI Forklift Safety System - Status Report", title_style))
        
        # General Info
        story.append(Paragraph("General Information", h2_style))
        story.append(Paragraph(f"<b>Timestamp:</b> {info['timestamp']}", body_style))
        story.append(Paragraph(f"<b>Machine Name:</b> {info['machine_name']}", body_style))
        story.append(Paragraph(f"<b>Operating System:</b> {info['os']}", body_style))
        
        # System Status
        story.append(Paragraph("System Status", h2_style))
        story.append(Paragraph(f"<b>Current User:</b> {info['current_user']} (Level {info['login_level']})", body_style))
        story.append(Paragraph(f"<b>Uptime:</b> {info['uptime']}", body_style))

        # Hardware & Health
        story.append(Paragraph("Hardware & Health", h2_style))
        story.append(Paragraph(f"<b>Relay Status:</b> {info['hw_status']}", body_style))
        story.append(Paragraph(f"<b>CPU Usage:</b> {info['cpu_usage']}%", body_style))
        story.append(Paragraph(f"<b>RAM Usage:</b> {info['ram_usage']}", body_style))
        story.append(Paragraph(f"<b>Disk Usage:</b> {info['disk_usage']}", body_style))

        # Camera Status
        story.append(Paragraph("Camera Status", h2_style))
        for cam in info['cameras']:
            status = "Online" if cam['connected'] else "Offline"
            active = "Yes" if cam['active'] else "No"
            breach = "YES" if cam['warning'] else "NO"
            text = f"<b>Station {cam['id']}:</b> {status} | Active: {active} | Objects: {cam['objects']} | Breach: {breach}"
            story.append(Paragraph(text, body_style))

        # Config Summary
        story.append(Paragraph("Configuration Summary", h2_style))
        story.append(Paragraph(f"<b>On-Delay:</b> {info['on_delay']}s", body_style))
        story.append(Paragraph(f"<b>Off-Delay:</b> {info['off_delay']}s", body_style))

        # Recent Logs
        story.append(Paragraph("Recent System Logs", h2_style))
        for log in info['recent_errors']:
            story.append(Paragraph(log, body_style))
            
        # Screenshots
        if screenshots:
            story.append(Paragraph("System Screenshots", h2_style))
            for ss_path in screenshots:
                if os.path.exists(ss_path):
                    # Wrap image and caption in KeepTogether to prevent orphan captions
                    elements = []
                    elements.append(Spacer(1, 0.2 * inch))
                    try:
                        img = RLImage(ss_path, width=6*inch, height=3.5*inch, kind='proportional')
                        elements.append(img)
                        elements.append(Paragraph(f"<i>{os.path.basename(ss_path)}</i>", body_style))
                        story.append(KeepTogether(elements))
                    except Exception as e:
                        story.append(Paragraph(f"Error loading image {ss_path}: {e}", body_style))

        doc.build(story)
        return filepath

    def capture_screenshot(self, widget: QWidget, name: str) -> str:
        """
        Captures a QWidget (must be called from GUI thread or safely via signals).
        This method assumes it's being called from a GUI-safe context before worker starts.
        Returns the saved file path.
        """
        if not widget:
            return ""
            
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp_str}.png"
        filepath = os.path.join(self.screenshots_dir, filename)
        
        pixmap = widget.grab()
        pixmap.save(filepath, "PNG")
        return filepath

    def build_zip_package(self, txt_path: str, pdf_path: str, screenshot_paths: list) -> str:
        """
        Compresses generated reports and screenshots into a single ZIP file.
        Returns the ZIP file path.
        """
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M")
        zip_filename = f"ReportPackage_{timestamp_str}.zip"
        zip_filepath = os.path.join(self.reports_dir, zip_filename)

        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if txt_path and os.path.exists(txt_path):
                zipf.write(txt_path, os.path.basename(txt_path))
            if pdf_path and os.path.exists(pdf_path):
                zipf.write(pdf_path, os.path.basename(pdf_path))
            for ss_path in screenshot_paths:
                if os.path.exists(ss_path):
                    # Put screenshots in a folder inside the ZIP
                    arcname = os.path.join("Screenshots", os.path.basename(ss_path))
                    zipf.write(ss_path, arcname)
                    
        return zip_filepath
