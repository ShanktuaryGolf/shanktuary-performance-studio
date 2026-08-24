import unittest
import tempfile
import os
import json


class TestDexterityAndScaling(unittest.TestCase):
    def test_dexterity_sign_transform(self):
        # RH golfer with +3.0 deg club path is In-to-Out
        rh_path = 3.0
        rh_str = f"Path: {abs(rh_path):.1f}° {'In To Out' if rh_path > 0 else 'Out To In'}"
        self.assertEqual(rh_str, "Path: 3.0° In To Out")

        # LH golfer with -3.0 deg raw path is In-to-Out for a lefty
        lh_path = -3.0
        lh_str = f"Path: {abs(lh_path):.1f}° {'In To Out' if lh_path < 0 else 'Out To In'}"
        self.assertEqual(lh_str, "Path: 3.0° In To Out")

    def test_foot_label_assignment(self):
        # RH: Left foot is Lead, Right foot is Trail
        is_left_handed = False
        l_label_rh = ("TRAIL FOOT (LEFT)" if is_left_handed else "LEAD FOOT (LEFT)")
        r_label_rh = ("LEAD FOOT (RIGHT)" if is_left_handed else "TRAIL FOOT (RIGHT)")
        self.assertEqual(l_label_rh, "LEAD FOOT (LEFT)")
        self.assertEqual(r_label_rh, "TRAIL FOOT (RIGHT)")

        # LH: Right foot is Lead, Left foot is Trail
        is_left_handed = True
        l_label_lh = ("TRAIL FOOT (LEFT)" if is_left_handed else "LEAD FOOT (LEFT)")
        r_label_lh = ("LEAD FOOT (RIGHT)" if is_left_handed else "TRAIL FOOT (RIGHT)")
        self.assertEqual(l_label_lh, "TRAIL FOOT (LEFT)")
        self.assertEqual(r_label_lh, "LEAD FOOT (RIGHT)")

    def test_scale_calculation_bounds(self):
        # Small window (laptop / 720p)
        quad_w, quad_h = 320, 200
        scale = max(0.85, min(2.5, min(quad_w / 380.0, quad_h / 230.0)))
        self.assertGreaterEqual(scale, 0.85)

        # 4K monitor (e.g. quad_w = 1200, quad_h = 700)
        quad_w, quad_h = 1200, 700
        scale_4k = max(0.85, min(2.5, min(quad_w / 380.0, quad_h / 230.0)))
        self.assertLessEqual(scale_4k, 2.5)
        self.assertGreater(scale_4k, 2.0)


if __name__ == "__main__":
    unittest.main()
