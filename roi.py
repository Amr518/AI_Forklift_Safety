from PyQt5.QtWidgets import QLabel, QSizePolicy
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtCore import pyqtSignal, QRect, QPoint, Qt, QSize

class VideoLabel(QLabel):
    """
    Custom QLabel widget that handles video frame rendering and provides an 
    interactive Region of Interest (ROI) overlay. Decouples drawing and drag-resize
    logic from the main window using PyQt signals.
    Maintains normalized coordinates [0.0, 1.0] to guarantee the ROI bounding box
    and display geometry remain perfectly locked across camera disconnections,
    reconnections, and window resize events.
    """
    # Emitted when the ROI has been updated (drawn, moved, or resized)
    roi_updated = pyqtSignal(QRect)

    HANDLE_SIZE = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        
        # State variables
        self.roi_rect = QRect()
        self.norm_roi = None      # (norm_x, norm_y, norm_w, norm_h) in [0.0, 1.0]
        self.is_editable = False  # Controlled by roles
        self.drawing_roi = False  # Set to True when "Draw ROI" button is clicked
        
        self.is_drawing = False
        self.dragging = False
        self.resizing = False
        
        self.resize_handle = None
        self.drag_offset = QPoint()
        self.start_point = QPoint()

    def sizeHint(self):
        # Stable invariant sizeHint prevents layout distortion when pixmaps change
        return QSize(320, 240)

    def minimumSizeHint(self):
        return QSize(160, 120)

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

    def set_roi(self, rect):
        """
        Programmatically sets the ROI boundary box and syncs normalized coordinates.
        """
        self.roi_rect = rect
        w = self.width()
        h = self.height()
        if w > 0 and h > 0 and rect is not None and not rect.isNull():
            self.norm_roi = (
                max(0.0, min(1.0, rect.x() / float(w))),
                max(0.0, min(1.0, rect.y() / float(h))),
                max(0.01, min(1.0, rect.width() / float(w))),
                max(0.01, min(1.0, rect.height() / float(h)))
            )
        self.update()

    def set_norm_roi(self, norm_tuple):
        """
        Sets ROI from normalized tuple (norm_x, norm_y, norm_w, norm_h) in [0.0, 1.0].
        Calculates pixel roi_rect based on current widget dimensions.
        """
        if norm_tuple and len(norm_tuple) == 4:
            nx, ny, nw, nh = norm_tuple
            nx = max(0.0, min(1.0, float(nx)))
            ny = max(0.0, min(1.0, float(ny)))
            nw = max(0.01, min(1.0 - nx, float(nw)))
            nh = max(0.01, min(1.0 - ny, float(nh)))
            self.norm_roi = (nx, ny, nw, nh)
            w = self.width()
            h = self.height()
            if w > 0 and h > 0:
                self.roi_rect = QRect(int(nx * w), int(ny * h), int(nw * w), int(nh * h))
            self.update()

    def get_norm_roi(self):
        """
        Returns the normalized ROI tuple (nx, ny, nw, nh) in [0.0, 1.0].
        """
        if self.norm_roi is not None:
            return self.norm_roi
        if not self.roi_rect.isNull() and self.width() > 0 and self.height() > 0:
            w = float(self.width())
            h = float(self.height())
            return (
                self.roi_rect.x() / w,
                self.roi_rect.y() / h,
                self.roi_rect.width() / w,
                self.roi_rect.height() / h
            )
        return None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        h = self.height()
        if self.norm_roi is not None and w > 0 and h > 0:
            nx, ny, nw, nh = self.norm_roi
            self.roi_rect = QRect(
                int(nx * w),
                int(ny * h),
                int(nw * w),
                int(nh * h)
            )
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
        elif self.drawing_roi:
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

        w = max(self.width(), 1)
        h = max(self.height(), 1)
        if not self.roi_rect.isNull():
            rx = max(0, min(self.roi_rect.x(), w - 5))
            ry = max(0, min(self.roi_rect.y(), h - 5))
            rw = max(5, min(self.roi_rect.width(), w - rx))
            rh = max(5, min(self.roi_rect.height(), h - ry))
            self.roi_rect = QRect(rx, ry, rw, rh)
            self.norm_roi = (
                rx / float(w),
                ry / float(h),
                rw / float(w),
                rh / float(h)
            )

        # Emit the update signal when interaction completes
        self.roi_updated.emit(self.roi_rect)
        self.update()

    # ==========================================
    # DRAW OVERLAY
    # ==========================================

    def paintEvent(self, event):
        # Draw background image first
        super().paintEvent(event)

        w = self.width()
        h = self.height()
        if (self.roi_rect is None or self.roi_rect.isNull()) and self.norm_roi is not None and w > 0 and h > 0:
            nx, ny, nw, nh = self.norm_roi
            self.roi_rect = QRect(int(nx * w), int(ny * h), int(nw * w), int(nh * h))

        roi = self.roi_rect
        if roi is None or roi.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw ROI Boundary (Red)
        pen = QPen(QColor(255, 59, 48), 3)
        painter.setPen(pen)
        painter.drawRect(roi)

        # Semi-transparent ROI Fill (Red with 40/255 opacity)
        painter.fillRect(roi, QColor(255, 59, 48, 40))

        # Render corner resize handles (White Squares)
        if self.is_editable:
            painter.setBrush(QColor(255, 255, 255))
            handles = self.get_handles(roi)
            for handle in handles.values():
                painter.drawRect(handle)
