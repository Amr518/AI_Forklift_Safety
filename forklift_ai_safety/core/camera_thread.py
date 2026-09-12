from PyQt5.QtCore import QThread, pyqtSignal, QRect
from PyQt5.QtGui import QImage
import cv2
import time
import numpy as np
from core.camera import Camera
from core.detector import YoloDetector
from core.alarm_manager import AlarmSystem

class CameraThread(QThread):
    """
    Independent camera processing thread. Automatically executes camera reading,
    runs YOLO detection in the background, checks ROI violations, and emits signals
    to the GUI thread to prevent blockages.
    """
    frame_processed = pyqtSignal(int, QImage, int, bool, float)
    camera_error = pyqtSignal(int, str)
    
    def __init__(self, cam_id, source=0, width=640, height=480):
        super().__init__()
        self.cam_id = cam_id
        self.source = source
        self.width = width
        self.height = height
        self.roi_rect = QRect()
        self._is_running = True
        self._is_enabled = True
        self.alarm_system = AlarmSystem()
        self.prev_time = 0
        
    def set_roi(self, rect):
        self.roi_rect = rect

    def set_source(self, new_source):
        self.source = new_source

    def set_enabled(self, enabled):
        self._is_enabled = enabled

    def stop(self):
        self._is_running = False
        self.wait()

    def run(self):
        # Initialize camera in the background thread scope
        camera = Camera(self.source, self.width, self.height)
        detector = None
        
        # If camera is set to simulation, bypass YOLO loading to save high memory/CPU usage
        is_simulated = isinstance(self.source, str) and self.source.startswith("Simulated")
        if not is_simulated:
            try:
                detector = YoloDetector("yolov8n.pt")
            except Exception as e:
                print(f"Error loading YOLO in thread {self.cam_id}: {e}")

        current_source = self.source
        
        while self._is_running:
            # Handle dynamic camera source switches from UI
            if current_source != self.source:
                camera.release()
                camera = Camera(self.source, self.width, self.height)
                current_source = self.source
                is_simulated = isinstance(self.source, str) and self.source.startswith("Simulated")
                if is_simulated:
                    detector = None
                else:
                    if detector is None:
                        try:
                            detector = YoloDetector("yolov8n.pt")
                        except Exception as e:
                            print(f"Error loading YOLO: {e}")
            
            # Handle standby state when monitoring is deactivated by operator
            if not self._is_enabled:
                standby_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                standby_frame[:] = (32, 23, 19)  # SCADA standby dark fill
                
                cv2.putText(standby_frame, f"STATION {self.cam_id + 1:02d} STANDBY", (120, 220), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (120, 140, 160), 2, cv2.LINE_AA)
                cv2.putText(standby_frame, "MONITORING DEACTIVATED", (170, 260), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (90, 100, 115), 1, cv2.LINE_AA)
                
                rgb_frame = cv2.cvtColor(standby_frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_frame.shape
                qt_image = QImage(rgb_frame.data, w, h, ch * w, QImage.Format_RGB888)
                
                # Emit standby HMI state
                self.frame_processed.emit(self.cam_id, qt_image.copy(), 0, False, 0.0)
                self.msleep(100)
                continue

            # Capture frame
            ret, frame, sim_detections = camera.read_frame()
            
            if not ret or frame is None:
                # Custom HMI Red Alert Connection Loss Panel
                offline_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                offline_frame[:] = (30, 20, 90)  # BGR Dark red alert
                
                cv2.putText(offline_frame, "⚠️ CRITICAL ALARM", (180, 180), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 255), 2, cv2.LINE_AA)
                cv2.putText(offline_frame, f"STATION {self.cam_id + 1:02d} CONNECTION LOST", (110, 220), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 255), 2, cv2.LINE_AA)
                cv2.putText(offline_frame, "VERIFY INTERFACE CONNECTION", (170, 260), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 200), 1, cv2.LINE_AA)
                
                rgb_frame = cv2.cvtColor(offline_frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_frame.shape
                qt_image = QImage(rgb_frame.data, w, h, ch * w, QImage.Format_RGB888)
                
                self.frame_processed.emit(self.cam_id, qt_image.copy(), 0, False, 0.0)
                self.camera_error.emit(self.cam_id, "Signal Offline")
                self.msleep(500)
                continue

            # Run detection
            persons = []
            if is_simulated and sim_detections is not None:
                # Ground truth detections directly from HMI simulator (lag-free CPU mode)
                persons = sim_detections
            elif detector is not None:
                try:
                    persons = detector.detect_persons(frame)
                except Exception as e:
                    print(f"YOLO error on station {self.cam_id}: {e}")

            # Check ROI Safety breaches
            warning = self.alarm_system.evaluate_safety(persons, self.roi_rect)

            # Draw targets: red bounding box for alert inside zone, orange for safe tracking
            for (x1, y1, x2, y2) in persons:
                color = (0, 0, 255) if warning else (255, 120, 0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label = "DANGER PATH DETECT" if warning else "TRACKING"
                cv2.putText(frame, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2, cv2.LINE_AA)

            # Render dynamic transparency highlight for the active ROI danger zone
            if self.roi_rect is not None and not self.roi_rect.isNull():
                rx, ry, rw, rh = self.roi_rect.x(), self.roi_rect.y(), self.roi_rect.width(), self.roi_rect.height()
                roi_color = (0, 0, 255) if warning else (0, 165, 255)
                cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), roi_color, 2)
                
                overlay = frame.copy()
                cv2.rectangle(overlay, (rx, ry), (rx + rw, ry + rh), roi_color, -1)
                alpha = 0.16 if warning else 0.05
                cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0.0, frame)
                cv2.putText(frame, "DANGER ZONE BOUNDS", (rx + 5, ry + 15), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, roi_color, 1, cv2.LINE_AA)

            # Calculate actual FPS inside the processing loop
            current_time = time.time()
            fps = 1.0 / (current_time - self.prev_time) if (current_time - self.prev_time) > 0.0 else 0.0
            self.prev_time = current_time
            
            # Format and convert raw frame to thread safe QImage
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            qt_image = QImage(frame_rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
            
            # Return visual frames and logical states
            self.frame_processed.emit(self.cam_id, qt_image, len(persons), warning, fps)
            self.msleep(15)

        camera.release()
