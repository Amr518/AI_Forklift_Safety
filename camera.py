import cv2

class Camera:
    """
    Manages OpenCV's VideoCapture interface, encapsulating setup, frame extraction,
    and device teardown.
    """
    def __init__(self, device_index=0, width=640, height=480):
        self.device_index = device_index
        self.width = width
        self.height = height
        self.cap = None
        try:
            self.initialize_camera()
        except Exception:
            self.cap = None

    def initialize_camera(self):
        try:
            import platform
            if platform.system() == 'Linux':
                self.cap = cv2.VideoCapture(self.device_index, cv2.CAP_V4L2)
            else:
                self.cap = cv2.VideoCapture(self.device_index)
            if self.cap is not None and self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            else:
                self.cap = None
        except Exception:
            self.cap = None


    def read_frame(self):
        """
        Reads a frame from the capture device.
        Returns:
            ret (bool): True if frame was successfully read, False otherwise.
            frame (numpy.ndarray or None): The captured image frame.
        """
        if self.cap is None or not self.cap.isOpened():
            return False, None
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return False, None
            return True, frame
        except Exception:
            return False, None

    def release(self):
        """
        Releases the OpenCV capture hardware.
        """
        if self.cap is not None:
            if self.cap.isOpened():
                self.cap.release()
            self.cap = None
