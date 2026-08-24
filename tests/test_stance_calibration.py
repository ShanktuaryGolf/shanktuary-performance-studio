import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from src.hardware.pressure.base import SensorReading
from obs_server import PressureManager


class TestStanceCalibration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cal_file = os.path.join(self.tmp_dir.name, "wbb_calibration.json")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_save_and_load_calibration(self):
        pm = PressureManager()
        pm.balance_multiplier = [1.05, 0.95]
        pm.board_mode = "dual"
        pm._save_calibration(filepath=self.cal_file)

        self.assertTrue(os.path.exists(self.cal_file))
        with open(self.cal_file, "r") as f:
            data = json.load(f)
        self.assertEqual(data["balance_multiplier"], [1.05, 0.95])

        # Test reload into fresh manager
        pm2 = PressureManager()
        pm2._load_calibration(filepath=self.cal_file)
        self.assertEqual(pm2.balance_multiplier, [1.05, 0.95])

    def test_stance_alignment_math(self):
        pm = PressureManager()
        # Simulate Left board reading 40kg, Right board reading 30kg for the same real weight
        samples = [(40.0, 30.0)] * 40
        pm._alignment_samples = samples
        pm._alignment_end_time = time.time() - 1.0
        pm._alignment_active = True

        # Process alignment completion
        pm._finish_stance_alignment()

        self.assertFalse(pm._alignment_active)
        mult_l, mult_r = pm.balance_multiplier
        # Target = 35kg. mult_l = 35/40 = 0.875, mult_r = 35/30 = 1.1667
        self.assertAlmostEqual(mult_l, 35.0 / 40.0, places=3)
        self.assertAlmostEqual(mult_r, 35.0 / 30.0, places=3)

        # After applying multipliers: Left = 40 * 0.875 = 35, Right = 30 * 1.1667 = 35 (50/50 balance)
        tared_left = 40.0 * mult_l
        tared_right = 30.0 * mult_r
        self.assertAlmostEqual(tared_left, tared_right, places=2)


if __name__ == "__main__":
    unittest.main()
