import os
import time
import zipfile
import shutil
from datetime import datetime
from PyQt5.QtCore import QThread, pyqtSignal

class StorageManager:
    """
    Independent Storage Manager.
    Handles cleanup of Reports, Screenshots, and Logs.
    Optionally archives them instead of deleting.
    """
    def __init__(self):
        self.project_dir = os.path.dirname(os.path.abspath(__file__))
        
    def _get_size_mb(self, file_path):
        try:
            return os.path.getsize(file_path) / (1024 * 1024)
        except OSError:
            return 0.0

    def _get_age_days(self, file_path, now):
        try:
            mtime = os.path.getmtime(file_path)
            return (now - mtime) / (24 * 3600)
        except OSError:
            return 0.0

    def cleanup_folder(self, folder_path, max_days, max_mb, archive_mode, archive_dir):
        """
        Cleans up a single folder based on retention policies.
        Returns a list of messages about deleted or archived files.
        """
        if not os.path.exists(folder_path):
            return []

        messages = []
        now = time.time()
        
        # Get list of files with their stats
        files = []
        for root, _, filenames in os.walk(folder_path):
            for name in filenames:
                file_path = os.path.join(root, name)
                files.append({
                    'path': file_path,
                    'name': name,
                    'mtime': os.path.getmtime(file_path),
                    'size': self._get_size_mb(file_path)
                })

        # Sort files by age (oldest first)
        files.sort(key=lambda x: x['mtime'])
        
        total_size = sum(f['size'] for f in files)
        
        for f in files:
            age_days = (now - f['mtime']) / (24 * 3600)
            
            # Check if file should be removed (older than max_days OR folder is over max_mb)
            remove_file = False
            if max_days > 0 and age_days > max_days:
                remove_file = True
            if max_mb > 0 and total_size > max_mb:
                remove_file = True
                
            if remove_file:
                try:
                    if archive_mode:
                        # Archive logic
                        file_dt = datetime.fromtimestamp(f['mtime'])
                        month_folder = file_dt.strftime("%Y-%m")
                        dest_dir = os.path.join(archive_dir, month_folder)
                        os.makedirs(dest_dir, exist_ok=True)
                        dest_path = os.path.join(dest_dir, f['name'])
                        
                        shutil.move(f['path'], dest_path)
                        messages.append(f"Archived: {f['name']}")
                    else:
                        # Delete logic
                        os.remove(f['path'])
                        messages.append(f"Deleted: {f['name']}")
                        
                    total_size -= f['size']
                except Exception as e:
                    messages.append(f"Error handling {f['name']}: {e}")
                    
        # If in archive mode, compress monthly folders that are older than current month
        if archive_mode and os.path.exists(archive_dir):
            current_month = datetime.now().strftime("%Y-%m")
            for item in os.listdir(archive_dir):
                item_path = os.path.join(archive_dir, item)
                if os.path.isdir(item_path) and item != current_month:
                    zip_path = os.path.join(archive_dir, f"archive_{item}.zip")
                    try:
                        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            for root, _, filenames in os.walk(item_path):
                                for file in filenames:
                                    file_path = os.path.join(root, file)
                                    arcname = os.path.relpath(file_path, item_path)
                                    zipf.write(file_path, arcname)
                        shutil.rmtree(item_path)
                        messages.append(f"Compressed archive: {item}")
                    except Exception as e:
                        messages.append(f"Error compressing archive {item}: {e}")

        return messages

    def run_cleanup(self, config):
        """
        Runs cleanup on all relevant folders based on config.
        config is a dict containing storage_settings.
        """
        messages = []
        
        storage_settings = config.get("storage_settings", {})
        if not storage_settings.get("auto_cleanup_enabled", False):
            return ["Auto-cleanup is disabled."]
            
        retention_days = storage_settings.get("retention_days", 30)
        max_reports_mb = storage_settings.get("max_reports_mb", 500)
        max_screenshots_mb = storage_settings.get("max_screenshots_mb", 200)
        max_logs_mb = storage_settings.get("max_logs_mb", 100)
        archive_mode = storage_settings.get("archive_mode", False)
        
        archive_dir = os.path.join(self.project_dir, storage_settings.get("archive_dir", "Archive"))
        if archive_mode:
            os.makedirs(archive_dir, exist_ok=True)
            
        report_settings = config.get("report_settings", {})
        reports_dir = os.path.join(self.project_dir, report_settings.get("reports_dir", "Reports"))
        screenshots_dir = os.path.join(reports_dir, "Screenshots")
        logs_dir = os.path.join(self.project_dir, "logs") # Assuming logs might be here, though the main system uses audit log in GUI. We'll clean email_history.json if needed, but it's a single file. We'll stick to cleaning Reports and Screenshots primarily, and the logs directory if it exists.
        
        # Cleanup Reports (excluding Screenshots subfolder if processed separately)
        # Note: cleanup_folder processes recursively, so we should clean Screenshots first,
        # or handle them carefully. We'll clean Screenshots first.
        messages.extend(self.cleanup_folder(screenshots_dir, retention_days, max_screenshots_mb, archive_mode, archive_dir))
        
        # Cleanup Reports (root files only, not traversing into Screenshots again ideally, but _cleanup_folder does os.walk. 
        # Since we just cleaned Screenshots, it's fine. We can just clean Reports.)
        # Actually, let's just use the Reports folder for both, since max_reports_mb can cover the whole thing.
        # But to be precise, let's adjust cleanup_folder to not recurse or just let it process everything under Reports with max_reports_mb.
        # The requirements say: Maximum Reports Folder Size, Maximum Screenshot Folder Size.
        # To support this, they must be separate folders or handled separately.
        # We will assume Reports contains ZIPs/PDFs/TXTs and Reports/Screenshots contains PNGs.
        
        # It's safer to just clean Reports/Screenshots with screenshot limits, and Reports (excluding Screenshots) with report limits.
        
        # Custom logic for Reports excluding Screenshots
        if os.path.exists(reports_dir):
            now = time.time()
            report_files = []
            for item in os.listdir(reports_dir):
                item_path = os.path.join(reports_dir, item)
                if os.path.isfile(item_path):
                    report_files.append({
                        'path': item_path,
                        'name': item,
                        'mtime': os.path.getmtime(item_path),
                        'size': self._get_size_mb(item_path)
                    })
            
            report_files.sort(key=lambda x: x['mtime'])
            total_size = sum(f['size'] for f in report_files)
            
            for f in report_files:
                age_days = (now - f['mtime']) / (24 * 3600)
                remove_file = False
                if retention_days > 0 and age_days > retention_days:
                    remove_file = True
                if max_reports_mb > 0 and total_size > max_reports_mb:
                    remove_file = True
                    
                if remove_file:
                    try:
                        if archive_mode:
                            file_dt = datetime.fromtimestamp(f['mtime'])
                            month_folder = file_dt.strftime("%Y-%m")
                            dest_dir = os.path.join(archive_dir, month_folder)
                            os.makedirs(dest_dir, exist_ok=True)
                            dest_path = os.path.join(dest_dir, f['name'])
                            shutil.move(f['path'], dest_path)
                            messages.append(f"Archived: {f['name']}")
                        else:
                            os.remove(f['path'])
                            messages.append(f"Deleted: {f['name']}")
                        total_size -= f['size']
                    except Exception as e:
                        messages.append(f"Error handling {f['name']}: {e}")

        # Logs directory
        if os.path.exists(logs_dir):
            messages.extend(self.cleanup_folder(logs_dir, retention_days, max_logs_mb, archive_mode, archive_dir))
            
        if not messages:
            messages.append("Cleanup finished. No files met criteria for removal/archiving.")
            
        return messages


class StorageWorker(QThread):
    """
    Background worker for executing storage cleanup without blocking the GUI.
    """
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.manager = StorageManager()

    def run(self):
        try:
            self.progress.emit("Starting storage cleanup...")
            messages = self.manager.run_cleanup(self.config)
            for msg in messages:
                self.progress.emit(msg)
            self.finished.emit(True, f"Cleanup completed. Processed {len(messages)} actions.")
        except Exception as e:
            self.finished.emit(False, f"Cleanup failed: {str(e)}")
