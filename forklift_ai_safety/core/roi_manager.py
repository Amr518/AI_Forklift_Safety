import os
import json
from PyQt5.QtCore import QRect

class RoiManager:
    """
    Manages loading, saving, and resolving Region of Interest (ROI) boundaries per camera index.
    """
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_dir = os.path.join(self.base_dir, "config")
        os.makedirs(self.config_dir, exist_ok=True)
        self.file_path = os.path.join(self.config_dir, "roi.json")
        self.rois = {}
        self.load_all_rois()

    def load_all_rois(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r") as f:
                    self.rois = json.load(f)
            except Exception as e:
                print(f"Error loading ROI configuration: {e}")
                self.rois = {}
        else:
            self.rois = {}

    def get_roi(self, cam_id):
        """
        Retrieves the saved QRect boundary for a specific camera ID.
        """
        key = f"cam_{cam_id}"
        if key in self.rois:
            coords = self.rois[key]
            x = coords.get("x")
            y = coords.get("y")
            w = coords.get("w")
            h = coords.get("h")
            if all(v is not None for v in [x, y, w, h]):
                return QRect(x, y, w, h)
        return QRect()

    def save_roi(self, cam_id, roi_rect):
        """
        Saves the QRect coordinates of an ROI for a given camera ID.
        """
        key = f"cam_{cam_id}"
        if roi_rect is None or roi_rect.isNull():
            self.rois[key] = {}
        else:
            self.rois[key] = {
                "x": roi_rect.x(),
                "y": roi_rect.y(),
                "w": roi_rect.width(),
                "h": roi_rect.height()
            }
            
        try:
            with open(self.file_path, "w") as f:
                json.dump(self.rois, f, indent=4)
        except Exception as e:
            print(f"Error saving ROI config for {key}: {e}")
stream = None
