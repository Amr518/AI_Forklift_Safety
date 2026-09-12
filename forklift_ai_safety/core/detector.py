import os
from ultralytics import YOLO

class YoloDetector:
    """
    Wraps the Ultralytics YOLO model and filters detections for target object classes (specifically persons).
    """
    def __init__(self, model_name="yolov8n.pt"):
        # Look for the pre-downloaded model weights in parent or local folder
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        parent_dir = os.path.dirname(base_dir)
        
        path_in_parent = os.path.join(parent_dir, model_name)
        path_in_base = os.path.join(base_dir, model_name)
        
        if os.path.exists(path_in_parent):
            model_path = path_in_parent
        elif os.path.exists(path_in_base):
            model_path = path_in_base
        else:
            model_path = model_name # Fallback to auto-download if missing
            
        self.model = YOLO(model_path)

    def detect_persons(self, frame):
        """
        Runs YOLO model inference on the given frame and filters for class 0 (person).
        Args:
            frame (numpy.ndarray): The input OpenCV frame.
        Returns:
            list of tuples: Bounding boxes of detected persons, formatted as [(x1, y1, x2, y2), ...]
        """
        results = self.model(frame, verbose=False)
        persons = []
        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                if cls == 0:  # Class 0 is Person in YOLO COCO model
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    persons.append((x1, y1, x2, y2))
        return persons
