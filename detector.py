import os
from ultralytics import YOLO

class YoloDetector:
    """
    Wraps the Ultralytics YOLO model and filters detections for target object classes (specifically persons).
    """
    def __init__(self, model_name="yolov8n.pt", confidence=0.25, model_path=None, **kwargs):
        if model_path is not None:
            model_name = model_path
        self.confidence = confidence
        self.model_name = model_name
        
        # Resolve the model path checking local directory and parent directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(base_dir)
        
        path_in_parent = os.path.join(parent_dir, model_name)
        path_in_base = os.path.join(base_dir, model_name)
        
        if os.path.exists(path_in_parent):
            model_path = path_in_parent
        elif os.path.exists(path_in_base):
            model_path = path_in_base
        else:
            model_path = model_name  # Will download automatically via ultralytics
            
        self.model = YOLO(model_path)

    def detect_persons(self, frame, conf=None, imgsz=320):
        """
        Runs YOLO model inference on the given frame and filters for class 0 (person).
        Args:
            frame (numpy.ndarray): The input OpenCV frame.
            conf (float, optional): Custom confidence threshold override.
            imgsz (int): YOLO inference input size.
        Returns:
            list of tuples: Bounding boxes of detected persons, formatted as [(x1, y1, x2, y2), ...]
        """
        c = conf if conf is not None else self.confidence
        results = self.model(frame, conf=c, imgsz=imgsz, verbose=False)
        persons = []
        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                if cls == 0:  # Class 0 is Person in YOLO COCO model
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    persons.append((x1, y1, x2, y2))
        return persons

