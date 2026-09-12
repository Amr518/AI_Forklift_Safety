from PyQt5.QtCore import QPoint, QRect

class AlarmSystem:
    """
    Manages safety status evaluation and alarm states. Determines if detected
    person bounding boxes violate the specified Region of Interest (ROI).
    """
    def __init__(self):
        self.warning_active = False

    def evaluate_safety(self, persons, roi_rect):
        """
        Evaluates whether any detected person's center point is within the ROI.
        Args:
            persons (list): List of (x1, y1, x2, y2) tuples.
            roi_rect (QRect): The active region of interest.
        Returns:
            bool: True if there is a safety warning/violation, False otherwise.
        """
        if roi_rect is None or roi_rect.isNull():
            return False

        for (x1, y1, x2, y2) in persons:
            center_x = int((x1 + x2) / 2)
            center_y = int((y1 + y2) / 2)
            
            # Check if person center falls within the ROI boundary
            if roi_rect.contains(QPoint(center_x, center_y)):
                return True
                
        return False

    def check_boundaries(self, persons, roi_rect):
        """
        Alias for evaluate_safety to maintain compatibility with new specifications.
        """
        return self.evaluate_safety(persons, roi_rect)

    def get_status_styles(self, warning):
        """
        Returns the appropriate text and stylesheet for the GUI status label based on current safety.
        Args:
            warning (bool): True if warning is active.
        Returns:
            tuple: (status_text, stylesheet_string)
        """
        if warning:
            text = "WARNING !!! PERSON DETECTED"
            stylesheet = """
                font-size: 22px;
                color: #FF3B30;
                font-weight: bold;
            """
        else:
            text = "SYSTEM SAFE"
            stylesheet = """
                font-size: 22px;
                color: #34C759;
                font-weight: bold;
            """
        return text, stylesheet

    def get_camera_error_styles(self):
        """
        Returns the status text and styling specifically for camera error or disconnection states.
        """
        text = "⚠️ CAMERA ERROR / DISCONNECTED"
        stylesheet = """
            font-size: 22px;
            color: #FF3B30;
            font-weight: bold;
        """
        return text, stylesheet
