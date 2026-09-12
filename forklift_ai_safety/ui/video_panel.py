from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtCore import pyqtSignal, QRect, QPoint, Qt

class VideoLabel(QLabel):
    """
    Custom QLabel widget that handles video frame rendering and provides an 
    interactive Region of Interest (ROI) overlay. Decouples drawing and drag-resize
    logic from the main window using PyQt signals.
    """
    # Emitted when the ROI has been updated (drawn, moved, or resized)
    roi_updated = pyqtSignal(QRect)

    HANDLE_SIZE = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        
        # State variables
        self.roi_rect = QRect()
        self.is_editable = False  # Controlled by supervisor/engineer roles
        self.drawing_roi = False  # Set to True when "Adjust ROI" button is clicked
        
        self.is_drawing = False
        self.dragging = False
        self.resizing = False
        
        self.resize_handle = None
        self.drag_offset = QPoint()
        self.start_point = QPoint()

    def set_editable(self, editable):
        """
        Enables or disables ROI interactions (drawing, resizing, moving).
        """
        self.is_editable = editable
        if not editable:
            self.setCursor(Qt.ArrowCursor)

    def start_drawing_roi(self):
        """
        Puts the widget into ROI drawing mode.
        """
        if self.is_editable:
            self.drawing_roi = True
            self.setCursor(Qt.CrossCursor)

    def set_roi(self, rect):
        """
        Programmatically sets the ROI boundary box and triggers redraw.
        """
        self.roi_rect = rect
        self.update()

    def get_handles(self, rect):
        """
        Calculates handle coordinates for the 4 corners of the ROI rectangle.
        """
        s = self.HANDLE_SIZE
        return {
            "top_left": QRect(rect.left() - s // 2, rect.top() - s // 2, s, s),
            "top_right": QRect(rect.right() - s // 2, rect.top() - s // 2, s, s),
            "bottom_left": QRect(rect.left() - s // 2, rect.bottom() - s // 2, s, s),
            "bottom_right": QRect(rect.right() - s // 2, rect.bottom() - s // 2, s, s)
        }

    def detect_handle(self, pos):
        """
        Detects if the mouse cursor is over one of the resize handles.
        """
        if self.roi_rect.isNull():
            return None
        handles = self.get_handles(self.roi_rect)
        for name, handle in handles.items():
            if handle.contains(pos):
                return name
        return None

    def update_cursor(self, pos):
        """
        Changes mouse cursor shape based on hover position (handles, ROI, or empty space).
        """
        if not self.is_editable or self.roi_rect.isNull():
            self.setCursor(Qt.ArrowCursor)
            return

        if self.drawing_roi:
            self.setCursor(Qt.CrossCursor)
            return

        handle = self.detect_handle(pos)
        rect = self.roi_rect

        if handle in ["top_left", "bottom_right"]:
            self.setCursor(Qt.SizeFDiagCursor)
        elif handle in ["top_right", "bottom_left"]:
            self.setCursor(Qt.SizeBDiagCursor)
        elif rect.contains(pos):
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    # ==========================================
    # MOUSE EVENTS
    # ==========================================

    def mousePressEvent(self, event):
        if not self.is_editable:
            return

        pos = event.pos()
        roi = self.roi_rect

        # 1. RESIZE Handle Dragged
        handle = self.detect_handle(pos)
        if handle:
            self.resizing = True
            self.resize_handle = handle
            return

        # 2. MOVE Existing ROI
        if not roi.isNull() and roi.contains(pos):
            self.dragging = True
            self.drag_offset = pos - roi.topLeft()

        # 3. DRAW New ROI
        elif self.drawing_roi or roi.isNull():
            self.is_drawing = True
            self.start_point = pos
            self.roi_rect = QRect(pos, pos)

        self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        self.update_cursor(pos)

        if not self.is_editable:
            return

        # 1. DRAW ROI
        if self.is_drawing:
            self.roi_rect = QRect(self.start_point, pos).normalized()
            self.update()

        # 2. MOVE ROI
        elif self.dragging:
            new_pos = pos - self.drag_offset
            rect = self.roi_rect
            rect.moveTo(new_pos)
            self.roi_rect = rect
            self.update()

        # 3. RESIZE ROI
        elif self.resizing:
            rect = self.roi_rect
            handle = self.resize_handle

            if handle == "top_left":
                rect.setTopLeft(pos)
            elif handle == "top_right":
                rect.setTopRight(pos)
            elif handle == "bottom_left":
                rect.setBottomLeft(pos)
            elif handle == "bottom_right":
                rect.setBottomRight(pos)

            self.roi_rect = rect.normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if not self.is_editable:
            return

        self.is_drawing = False
        self.dragging = False
        self.resizing = False
        self.drawing_roi = False

        # Emit the update signal when interaction completes
        self.roi_updated.emit(self.roi_rect)
        self.update()

    # ==========================================
    # DRAW OVERLAY
    # ==========================================

    def paintEvent(self, event):
        # Draw background video image
        super().paintEvent(event)

        roi = self.roi_rect
        if roi is None or roi.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw ROI Boundary (bright orange-red for active HMI visibility)
        pen = QPen(QColor(255, 120, 0), 2, Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(roi)

        # Semi-transparent ROI Danger Zone Fill
        painter.fillRect(roi, QColor(255, 120, 0, 30))

        # Render corner resize handles (White Squares) when unlocked
        if self.is_editable:
            painter.setBrush(QColor(255, 255, 255))
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            handles = self.get_handles(roi)
            for handle in handles.values():
                painter.drawRect(handle)
