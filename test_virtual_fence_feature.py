"""
Test verification script for Virtual Fence Horizontal & Vertical line toggle and position adjustment.
"""

import os
import sys
import unittest
import numpy as np

# Ensure workspace root in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.models import TrackedObject
from core.virtual_fence import VirtualFence
from core.multi_camera_manager import MultiCameraManager


class TestVirtualFenceFeature(unittest.TestCase):

    def test_horizontal_fence_endpoints(self):
        fence = VirtualFence(
            fence_id="vf_cam1",
            fence_type="horizontal",
            position=60.0,
            name="Horizontal Sector Line"
        )
        p1, p2 = fence.get_endpoints(frame_w=640, frame_h=480)
        self.assertEqual(p1, (0, 288))
        self.assertEqual(p2, (640, 288))

    def test_vertical_fence_endpoints(self):
        fence = VirtualFence(
            fence_id="vf_cam2",
            fence_type="vertical",
            position=30.0,
            name="Vertical Sector Line"
        )
        p1, p2 = fence.get_endpoints(frame_w=640, frame_h=480)
        self.assertEqual(p1, (192, 0))
        self.assertEqual(p2, (192, 480))

    def test_horizontal_fence_intrusion_detection(self):
        fence = VirtualFence(
            fence_id="vf_test",
            fence_type="horizontal",
            position=50.0,  # y = 240 for 480h
            name="Midline"
        )

        track = TrackedObject(
            track_id=101,
            centroid=(320, 260),
            box=(300, 240, 340, 280),
            class_name="human",
            confidence=0.88,
            first_seen=1.0,
            last_seen=2.0,
            history=[(1.0, (320, 220)), (2.0, (320, 260))]
        )

        alert = fence.check_intrusion(track, "cam1", "Camera 1", "Sector A", frame_w=640, frame_h=480)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.event_type, "intrusion")
        self.assertIn("vf_test", track.crossed_fences)

        # Ensure single-trigger (no duplicate alert)
        dup_alert = fence.check_intrusion(track, "cam1", "Camera 1", "Sector A", frame_w=640, frame_h=480)
        self.assertIsNone(dup_alert)

    def test_vertical_fence_intrusion_detection(self):
        fence = VirtualFence(
            fence_id="vf_vtest",
            fence_type="vertical",
            position=50.0,  # x = 320 for 640w
            name="Vertical Line"
        )

        track = TrackedObject(
            track_id=202,
            centroid=(350, 200),
            box=(330, 180, 370, 220),
            class_name="human",
            confidence=0.91,
            first_seen=1.0,
            last_seen=2.0,
            history=[(1.0, (300, 200)), (2.0, (350, 200))]
        )

        alert = fence.check_intrusion(track, "cam1", "Camera 1", "Sector B", frame_w=640, frame_h=480)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.event_type, "intrusion")

    def test_manager_dynamic_update_fence(self):
        mgr = MultiCameraManager(config_path="config/cameras.json", supabase_manager=None)
        self.assertGreater(len(mgr.camera_configs), 0)
        target_cam_id = mgr.camera_configs[0]["id"]

        # Enable horizontal fence
        updated = mgr.update_camera_fence(target_cam_id, {
            "enabled": True,
            "type": "horizontal",
            "position": 45,
            "name": "Live Test Fence"
        })
        self.assertIsNotNone(updated)
        self.assertTrue(updated["virtual_fence"]["enabled"])
        self.assertEqual(updated["virtual_fence"]["type"], "horizontal")
        self.assertEqual(updated["virtual_fence"]["position"], 45.0)

        # Switch to vertical fence at 70%
        updated2 = mgr.update_camera_fence(target_cam_id, {
            "enabled": True,
            "type": "vertical",
            "position": 70,
            "name": "Live Vert Fence"
        })
        self.assertTrue(updated2["virtual_fence"]["enabled"])
        self.assertEqual(updated2["virtual_fence"]["type"], "vertical")
        self.assertEqual(updated2["virtual_fence"]["position"], 70.0)

        # Disable fence
        updated3 = mgr.update_camera_fence(target_cam_id, {
            "enabled": False,
            "type": "vertical",
            "position": 70
        })
        self.assertFalse(updated3["virtual_fence"]["enabled"])


if __name__ == "__main__":
    unittest.main()
