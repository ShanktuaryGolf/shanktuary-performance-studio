"""Unit tests for Center of Pressure (COP) and Biomechanical Math."""

import unittest

from src.hardware.pressure.base import (
    BOARD_LENGTH,
    BOARD_WIDTH,
    SensorReading,
    TareOffsets,
)
from src.processing.pressure.cop import BodyWeightNormalizer, CoPCalculator
from src.processing.pressure.torque import TorqueCalculator


class TestPressureCOP(unittest.TestCase):
    def setUp(self):
        self.calc = CoPCalculator(noise_floor_kg=0.1)

    def test_centered_load(self):
        # 20kg equally on all 4 sensors
        reading = SensorReading(top_left=20.0, top_right=20.0, bottom_left=20.0, bottom_right=20.0, timestamp=1.0)
        cop = self.calc.compute(reading)
        self.assertIsNotNone(cop)
        self.assertAlmostEqual(cop.total_kg, 80.0)
        self.assertAlmostEqual(cop.cop_x, 0.0, places=2)
        self.assertAlmostEqual(cop.cop_y, 0.0, places=2)
        self.assertAlmostEqual(cop.pct_left, 50.0, places=1)
        self.assertAlmostEqual(cop.pct_right, 50.0, places=1)

    def test_left_foot_load(self):
        # 40kg on left sensors, 0kg on right sensors
        reading = SensorReading(top_left=20.0, top_right=0.0, bottom_left=20.0, bottom_right=0.0, timestamp=2.0)
        cop = self.calc.compute(reading)
        self.assertIsNotNone(cop)
        self.assertAlmostEqual(cop.pct_left, 100.0)
        self.assertAlmostEqual(cop.pct_right, 0.0)
        self.assertAlmostEqual(cop.cop_x, -BOARD_WIDTH / 2, places=2)

    def test_tare_offset(self):
        tare = TareOffsets(top_left=2.0, top_right=1.0, bottom_left=1.5, bottom_right=0.5)
        raw = SensorReading(top_left=22.0, top_right=21.0, bottom_left=21.5, bottom_right=20.5, timestamp=3.0)
        tared = tare.apply(raw)
        self.assertAlmostEqual(tared.top_left, 20.0)
        self.assertAlmostEqual(tared.top_right, 20.0)
        self.assertAlmostEqual(tared.bottom_left, 20.0)
        self.assertAlmostEqual(tared.bottom_right, 20.0)

    def test_bodyweight_normalizer(self):
        norm = BodyWeightNormalizer()
        for _ in range(60):
            norm.feed(80.0)
        self.assertTrue(norm.is_calibrated)
        self.assertAlmostEqual(norm.bodyweight_kg, 80.0)
        self.assertAlmostEqual(norm.normalize(120.0), 1.5, places=2)

    def test_torque_calculator(self):
        t_calc = TorqueCalculator()
        reading = SensorReading(top_left=10.0, top_right=30.0, bottom_left=30.0, bottom_right=10.0, timestamp=4.0)
        cop = self.calc.compute(reading)
        torque = t_calc.update(cop)
        self.assertGreater(torque.torque_nm, 0.0)

if __name__ == '__main__':
    unittest.main()
