import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from obs_server import PressureManager
from src.hardware.pressure.base import SensorReading


class TestStanceCalibration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cal_file = os.path.join(self.tmp_dir.name, "wbb_calibration.json")
        # A finished alignment calls _save_calibration() with no path, which
        # wrote this test's multipliers over the user's real calibration.
        p = patch("obs_server.CALIBRATION_FILE", self.cal_file)
        p.start()
        self.addCleanup(p.stop)

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
        # Feed a complete live hold instead of bypassing the safety guards.
        pm.backend = SimpleNamespace(is_open=True)
        with patch("obs_server.time.monotonic", return_value=100) as sensor_clock, \
                patch("obs_server.time.time", return_value=1000) as wall_clock:
            pm._latest_raw_reading = SensorReading(20, 15, 20, 15, 100)
            pm.start_stance_alignment(delay_sec=0, duration_sec=4)
            for i in range(41):
                sensor_clock.return_value = 100 + i / 10
                wall_clock.return_value = 1000 + i / 10
                reading = SensorReading(20, 15, 20, 15, sensor_clock.return_value)
                pm._latest_raw_reading = reading
                pm._advance_stance_alignment(reading)

        self.assertFalse(pm._alignment_active)
        mult_l, mult_r = pm.balance_multiplier
        # Target = 35kg. mult_l = 35/40 = 0.875, mult_r = 35/30 = 1.1667
        self.assertAlmostEqual(mult_l, 35.0 / 40.0, places=3)
        self.assertAlmostEqual(mult_r, 35.0 / 30.0, places=3)

        # After applying multipliers: Left = 40 * 0.875 = 35, Right = 30 * 1.1667 = 35 (50/50 balance)
        tared_left = 40.0 * mult_l
        tared_right = 30.0 * mult_r
        self.assertAlmostEqual(tared_left, tared_right, places=2)

    def test_lead_in_countdown_status(self):
        pm = PressureManager()
        pm.backend = SimpleNamespace(is_open=True)
        pm._latest_raw_reading = SensorReading(20, 15, 20, 15, time.monotonic())
        res = pm.start_stance_alignment(delay_sec=5.0, duration_sec=4.0)
        self.assertEqual(res["delay_sec"], 5.0)
        self.assertEqual(res["duration_sec"], 4.0)

        st = pm.get_alignment_status()
        self.assertTrue(st["active"])
        self.assertGreater(st["remaining_sec"], 4.0)
        self.assertIn("Step onto boards", st["message"])


if __name__ == "__main__":
    unittest.main()
