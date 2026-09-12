from PyQt5.QtCore import QPoint, QRect

class AlarmSystem:
    """
    Manages safety status evaluation and alarm states. Determines if detected
    person bounding boxes violate the specified Region of Interest (ROI).
    """
    def __init__(self):
        pass

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
