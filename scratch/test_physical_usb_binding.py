import os
import sys
import unittest
import tempfile
import json
import shutil
import numpy as np
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_gui_system
from ai_gui_system import (
    get_physical_usb_path,
    persist_station_physical_path,
    get_usb_camera_details,
    is_camera_node_match,
    CameraWorkerThread
)

class TestPhysicalUSBBinding(unittest.TestCase):
    def setUp(self):
        CameraWorkerThread.active_physical_paths.clear()
        CameraWorkerThread.active_device_indices.clear()

    def tearDown(self):
        CameraWorkerThread.active_physical_paths.clear()
        CameraWorkerThread.active_device_indices.clear()

    def test_get_physical_usb_path_nonexistent(self):
        """Non-existent device should return None gracefully."""
        self.assertIsNone(get_physical_usb_path("/dev/video999"))
        self.assertIsNone(get_physical_usb_path(999))
        self.assertIsNone(get_physical_usb_path(None))

    def test_get_physical_usb_path_resolution(self):
        """Test physical USB bus string extraction from mocked sysfs paths."""
        with patch("ai_gui_system.os.path.exists") as mock_exists, \
             patch("ai_gui_system.os.path.realpath") as mock_realpath:
            
            mock_exists.return_value = True
            # Hub case: /sys/devices/.../usb1/1-1/1-1.2/1-1.2:1.0 -> 1-1.2
            mock_realpath.return_value = "/sys/devices/pci0000:00/0000:00:14.0/usb1/1-1/1-1.2/1-1.2:1.0"
            res = get_physical_usb_path("/dev/video0")
            self.assertEqual(res, "1-1.2")

            # Direct port case: /sys/devices/.../usb1/1-4/1-4:1.0 -> 1-4
            mock_realpath.return_value = "/sys/devices/pci0000:00/0000:00:14.0/usb1/1-4/1-4:1.0"
            res2 = get_physical_usb_path("/dev/video2")
            self.assertEqual(res2, "1-4")

    def test_camera_worker_thread_registry(self):
        """Verify class-level thread safety sets and locks."""
        self.assertTrue(hasattr(CameraWorkerThread, "active_physical_paths"))
        self.assertTrue(hasattr(CameraWorkerThread, "active_device_indices"))
        self.assertTrue(hasattr(CameraWorkerThread, "_registry_lock"))
        self.assertIsInstance(CameraWorkerThread.active_physical_paths, set)
        self.assertIsInstance(CameraWorkerThread.active_device_indices, set)

    def test_strict_match_gate_prevents_swapping(self):
        """
        Verify that _scan_for_camera strictly ignores candidate nodes
        whose physical USB path does not match target_physical_usb_path.
        """
        worker = CameraWorkerThread(
            device_index="/dev/video0",
            station_id=0,
            target_physical_usb_path="1-1.2"
        )

        with patch.object(ai_gui_system.glob, "glob", return_value=["/dev/video0", "/dev/video2"]), \
             patch.object(ai_gui_system, "get_physical_usb_path") as mock_phys, \
             patch.object(ai_gui_system, "Camera") as mock_cam_cls:

            def phys_lookup(node):
                if node == "/dev/video0":
                    return "1-1.4"  # Wrong port
                elif node == "/dev/video2":
                    return "1-1.2"  # Exact matching port
                return None
            mock_phys.side_effect = phys_lookup

            mock_cam_inst = MagicMock()
            mock_cam_inst.cap.isOpened.return_value = True
            mock_cam_inst.read_frame.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cam_cls.return_value = mock_cam_inst

            found = worker._scan_for_camera()
            self.assertTrue(found, "Should find and bind candidate on matching physical USB port")
            self.assertEqual(worker.current_physical_path, "1-1.2")
            self.assertEqual(worker.current_device_index, "/dev/video2")
            self.assertIn("1-1.2", CameraWorkerThread.active_physical_paths)
            self.assertIn("/dev/video2", CameraWorkerThread.active_device_indices)

            # Cleanup
            worker._release_camera_locked()
            self.assertNotIn("1-1.2", CameraWorkerThread.active_physical_paths)
            self.assertNotIn("/dev/video2", CameraWorkerThread.active_device_indices)

    def test_conflict_gate(self):
        """Verify that a node/path already claimed by another thread is ignored."""
        CameraWorkerThread.active_physical_paths.add("1-1.2")
        CameraWorkerThread.active_device_indices.add("/dev/video0")
        CameraWorkerThread.active_device_indices.add(0)

        worker = CameraWorkerThread(
            device_index="/dev/video0",
            station_id=1,
            target_physical_usb_path="1-1.2"
        )

        with patch.object(ai_gui_system.glob, "glob", return_value=["/dev/video0"]), \
             patch.object(ai_gui_system, "get_physical_usb_path", return_value="1-1.2"), \
             patch.object(ai_gui_system, "Camera") as mock_cam_cls:

            found = worker._scan_for_camera()
            self.assertFalse(found, "Should NOT claim node or path that is already active in registry")
            mock_cam_cls.assert_not_called()

    def test_disconnection_and_cleanup(self):
        """Verify release_camera_locked cleanly purges registry."""
        worker = CameraWorkerThread(device_index="/dev/video0", station_id=0, target_physical_usb_path="1-1.2")
        worker.current_physical_path = "1-1.2"
        worker.current_device_index = "/dev/video0"
        mock_cam = MagicMock()
        worker.camera = mock_cam

        CameraWorkerThread.active_physical_paths.add("1-1.2")
        CameraWorkerThread.active_device_indices.add("/dev/video0")
        CameraWorkerThread.active_device_indices.add(0)

        worker._release_camera_locked()

        self.assertIsNone(worker.current_physical_path)
        self.assertIsNone(worker.current_device_index)
        self.assertIsNone(worker.camera)
        mock_cam.release.assert_called_once()
        self.assertNotIn("1-1.2", CameraWorkerThread.active_physical_paths)
        self.assertNotIn("/dev/video0", CameraWorkerThread.active_device_indices)
        self.assertNotIn(0, CameraWorkerThread.active_device_indices)

    def test_auto_detection_and_persistence(self):
        """Verify that initial boot auto-detects and persists target physical path."""
        worker = CameraWorkerThread(device_index="/dev/video0", station_id=2, target_physical_usb_path=None)
        
        with patch.object(ai_gui_system.glob, "glob", return_value=["/dev/video4"]), \
             patch.object(ai_gui_system, "get_physical_usb_path", return_value="1-1.3"), \
             patch.object(ai_gui_system, "persist_station_physical_path") as mock_persist, \
             patch.object(ai_gui_system, "Camera") as mock_cam_cls:

            mock_cam_inst = MagicMock()
            mock_cam_inst.cap.isOpened.return_value = True
            mock_cam_inst.read_frame.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cam_cls.return_value = mock_cam_inst

            found = worker._scan_for_camera()
            self.assertTrue(found)
            self.assertEqual(worker.target_physical_usb_path, "1-1.3")
            mock_persist.assert_called_once_with(2, "1-1.3")

    def test_is_camera_node_match(self):
        """Verify is_camera_node_match handles physical ports, serials, and device nodes."""
        # None target matches any candidate
        self.assertTrue(is_camera_node_match("/dev/video0", None))

        # Direct node matches
        self.assertTrue(is_camera_node_match("/dev/video0", "/dev/video0"))
        self.assertTrue(is_camera_node_match("/dev/video0", 0))

        # Mock get_usb_camera_details for rich matching
        mock_details = {
            "node": "/dev/video0",
            "physical_port": "1-1.2",
            "serial": "SN98765",
            "product": "HD Camera",
            "by_path": "/dev/v4l/by-path/pci-0000:00:14.0-usb-0:1.2:1.0-video-index0",
            "by_id": "/dev/v4l/by-id/usb-Vendor_HD_Camera_SN98765-video-index0"
        }

        with patch("ai_gui_system.get_usb_camera_details", return_value=mock_details), \
             patch("ai_gui_system.get_physical_usb_path", return_value="1-1.2"):
            # Match physical port
            self.assertTrue(is_camera_node_match("/dev/video0", "1-1.2"))
            self.assertFalse(is_camera_node_match("/dev/video0", "1-1.4"))

            # Match serial number (both plain and with serial: prefix)
            self.assertTrue(is_camera_node_match("/dev/video0", "SN98765"))
            self.assertTrue(is_camera_node_match("/dev/video0", "serial:SN98765"))
            self.assertFalse(is_camera_node_match("/dev/video0", "serial:WRONG_SERIAL"))

            # Match by-id
            self.assertTrue(is_camera_node_match("/dev/video0", "/dev/v4l/by-id/usb-Vendor_HD_Camera_SN98765-video-index0"))

    def test_serial_based_camera_binding(self):
        """Verify worker binds to camera matching serial number target."""
        worker = CameraWorkerThread(
            device_index="/dev/video0",
            station_id=1,
            target_physical_usb_path="serial:CAM_FRONT_001"
        )

        def mock_details_fn(node):
            if node == "/dev/video0":
                return {"node": "/dev/video0", "physical_port": "1-1.2", "serial": "CAM_REAR_002"}
            elif node == "/dev/video2":
                return {"node": "/dev/video2", "physical_port": "1-1.4", "serial": "CAM_FRONT_001"}
            return None

        with patch.object(ai_gui_system.glob, "glob", return_value=["/dev/video0", "/dev/video2"]), \
             patch("ai_gui_system.get_usb_camera_details", side_effect=mock_details_fn), \
             patch("ai_gui_system.get_physical_usb_path", side_effect=lambda n: "1-1.2" if n == "/dev/video0" else "1-1.4"), \
             patch.object(ai_gui_system, "Camera") as mock_cam_cls:

            mock_cam_inst = MagicMock()
            mock_cam_inst.cap.isOpened.return_value = True
            mock_cam_inst.read_frame.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cam_cls.return_value = mock_cam_inst

            found = worker._scan_for_camera()
            self.assertTrue(found)
            self.assertEqual(worker.current_device_index, "/dev/video2")
            worker._release_camera_locked()


if __name__ == "__main__":
    unittest.main()
