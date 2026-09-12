import cv2
import numpy as np
import time
import random

class SimulatedCamera:
    """
    Generates a premium simulated warehouse HMI visual stream with moving workers
    and forklift zones to allow testing 4 concurrent feeds without cameras.
    """
    def __init__(self, cam_id, width=640, height=480):
        self.cam_id = cam_id
        self.width = width
        self.height = height
        
        # Configure unique speed & starting parameters per camera to make them distinct
        random.seed(cam_id * 100)
        self.p1_x = random.randint(50, 200)
        self.p1_y = random.randint(120, 360)
        self.p1_dx = random.choice([2, 3, 4])
        self.p1_dy = random.choice([-1, 1]) * random.uniform(0.5, 1.5)
        
        self.p2_x = random.randint(350, 580)
        self.p2_y = random.randint(100, 300)
        self.p2_dx = random.choice([-2, -3, -4])
        self.p2_dy = random.choice([-1, 1]) * random.uniform(0.5, 1.5)

    def read_frame(self):
        # Create dark premium industrial SCADA background (hex #0e121a)
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame[:] = (26, 18, 14)  # BGR representation of deep charcoal/blue
        
        # Draw SCADA floor grids
        grid_size = 40
        for x in range(0, self.width, grid_size):
            cv2.line(frame, (x, 0), (x, self.height), (38, 29, 24), 1)
        for y in range(0, self.height, grid_size):
            cv2.line(frame, (0, y), (self.width, y), (38, 29, 24), 1)
            
        # Draw simulated structural warehouse obstacles
        # Station Rack 1
        cv2.rectangle(frame, (40, 40), (160, 90), (52, 41, 33), -1)
        cv2.rectangle(frame, (40, 40), (160, 90), (74, 59, 48), 2)
        cv2.putText(frame, f"BAY A-0{self.cam_id+1}", (50, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 120, 100), 1, cv2.LINE_AA)
        
        # Station Rack 2
        cv2.rectangle(frame, (480, 380), (600, 430), (52, 41, 33), -1)
        cv2.rectangle(frame, (480, 380), (600, 430), (74, 59, 48), 2)
        cv2.putText(frame, "CARGO BND", (495, 410), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 120, 100), 1, cv2.LINE_AA)

        # Animate Pedestrian 1
        self.p1_x += self.p1_dx
        self.p1_y += self.p1_dy
        if self.p1_x < 30 or self.p1_x > self.width - 30:
            self.p1_dx *= -1
        if self.p1_y < 100 or self.p1_y > self.height - 100:
            self.p1_dy *= -1
            
        # Animate Pedestrian 2
        self.p2_x += self.p2_dx
        self.p2_y += self.p2_dy
        if self.p2_x < 30 or self.p2_x > self.width - 30:
            self.p2_dx *= -1
        if self.p2_y < 100 or self.p2_y > self.height - 100:
            self.p2_dy *= -1

        # Draw forklift graphic
        fl_x, fl_y = 320, 240
        # Yellow body
        cv2.rectangle(frame, (fl_x - 25, fl_y - 20), (fl_x + 25, fl_y + 20), (0, 190, 240), -1)
        cv2.rectangle(frame, (fl_x - 25, fl_y - 20), (fl_x + 25, fl_y + 20), (0, 220, 255), 2)
        # Forklift tyres
        cv2.circle(frame, (fl_x - 15, fl_y - 22), 5, (10, 10, 10), -1)
        cv2.circle(frame, (fl_x + 15, fl_y - 22), 5, (10, 10, 10), -1)
        cv2.circle(frame, (fl_x - 15, fl_y + 22), 5, (10, 10, 10), -1)
        cv2.circle(frame, (fl_x + 15, fl_y + 22), 5, (10, 10, 10), -1)
        # Mast lines
        cv2.line(frame, (fl_x + 25, fl_y - 12), (fl_x + 40, fl_y - 12), (180, 180, 180), 2)
        cv2.line(frame, (fl_x + 25, fl_y + 12), (fl_x + 40, fl_y + 12), (180, 180, 180), 2)
        cv2.putText(frame, "FL-01", (fl_x - 18, fl_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA)

        # Draw Pedestrian 1 Silhouette
        p1_cx, p1_cy = int(self.p1_x), int(self.p1_y)
        cv2.circle(frame, (p1_cx, p1_cy - 12), 6, (180, 120, 255), -1)
        cv2.rectangle(frame, (p1_cx - 8, p1_cy - 6), (p1_cx + 8, p1_cy + 14), (180, 120, 255), -1)
        cv2.putText(frame, f"P-01", (p1_cx - 12, p1_cy + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (220, 180, 255), 1, cv2.LINE_AA)

        # Draw Pedestrian 2 Silhouette
        p2_cx, p2_cy = int(self.p2_x), int(self.p2_y)
        cv2.circle(frame, (p2_cx, p2_cy - 12), 6, (255, 180, 120), -1)
        cv2.rectangle(frame, (p2_cx - 8, p2_cy - 6), (p2_cx + 8, p2_cy + 14), (255, 180, 120), -1)
        cv2.putText(frame, f"P-02", (p2_cx - 12, p2_cy + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 220, 180), 1, cv2.LINE_AA)

        # Bottom Station Information Overlay
        time_str = time.strftime("%H:%M:%S")
        cv2.putText(frame, f"SYS FEED STATION {self.cam_id + 1:02d} | SIM | {time_str}", (15, self.height - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (110, 125, 140), 1, cv2.LINE_AA)

        # Output ground-truth bboxes of the moving workers (x1, y1, x2, y2)
        detections = [
            (p1_cx - 12, p1_cy - 20, p1_cx + 12, p1_cy + 20),
            (p2_cx - 12, p2_cy - 20, p2_cx + 12, p2_cy + 20)
        ]
        
        return True, frame, detections


class Camera:
    """
    Manages OpenCV's VideoCapture interface, encapsulating setup, frame extraction,
    and device teardown. Supports simulated streams.
    """
    def __init__(self, device_index=0, width=640, height=480):
        self.device_index = device_index
        self.width = width
        self.height = height
        self.cap = None
        self.simulated_cam = None
        self.initialize_camera()

    def initialize_camera(self):
        # Check if the device index represents the Simulated Factory Mode
        if isinstance(self.device_index, str) and self.device_index.startswith("Simulated"):
            # Extract station ID
            try:
                station_id = int(self.device_index.split("_")[1])
            except Exception:
                station_id = 0
            self.simulated_cam = SimulatedCamera(station_id, self.width, self.height)
            return

        # Attempt standard CV2 initialization
        try:
            # If device index is string (e.g. RTSP or local video file)
            if isinstance(self.device_index, str):
                self.cap = cv2.VideoCapture(self.device_index)
            else:
                self.cap = cv2.VideoCapture(int(self.device_index))
            
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        except Exception:
            self.cap = None

    def read_frame(self):
        """
        Reads a frame from the capture device.
        Returns:
            ret (bool): True if frame was successfully read, False otherwise.
            frame (numpy.ndarray or None): The captured image frame.
            simulated_detections (list or None): Simulated person positions if simulated.
        """
        if self.simulated_cam is not None:
            return self.simulated_cam.read_frame()

        if self.cap is None or not self.cap.isOpened():
            return False, None, None
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return False, None, None
            # Standard camera does not provide simulated detections
            return True, frame, None
        except Exception:
            return False, None, None

    def release(self):
        """
        Releases the OpenCV capture hardware.
        """
        if self.cap is not None:
            if self.cap.isOpened():
                self.cap.release()
            self.cap = None
        self.simulated_cam = None
