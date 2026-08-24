"""Unit tests for Shot-Synchronized Pressure Buffer."""

import unittest
import time
from src.hardware.pressure.base import SensorReading
from src.processing.pressure.cop import CoPCalculator
from src.processing.pressure.buffer import ShotSynchronizedPressureBuffer

class TestPressureBuffer(unittest.TestCase):
    def setUp(self):
        self.buf = ShotSynchronizedPressureBuffer(capacity=100)
        self.calc = CoPCalculator()

    def test_buffer_push_and_retrieval(self):
        reading = SensorReading(top_left=20.0, top_right=20.0, bottom_left=20.0, bottom_right=20.0, timestamp=10.0)
        cop = self.calc.compute(reading)
        frame = self.buf.push(cop, phase='Address')
        self.assertEqual(frame['total_kg'], 80.0)
        self.assertEqual(frame['phase'], 'Address')
        latest = self.buf.get_latest_frame()
        self.assertEqual(latest['timestamp'], 10.0)

    def test_shot_impact_trigger_sync(self):
        captured_data = []
        def on_shot_captured(frames):
            captured_data.extend(frames)

        base_t = time.time()
        # Feed 10 frames pre-impact
        for i in range(10):
            t = base_t + i * 0.016
            reading = SensorReading(top_left=20.0, top_right=20.0, bottom_left=20.0, bottom_right=20.0, timestamp=t)
            cop = self.calc.compute(reading)
            self.buf.push(cop, phase='Backswing')

        # Trigger impact
        impact_t = base_t + 10 * 0.016
        self.buf._post_impact_target = 5 # small target for test
        self.buf.trigger_shot_impact(impact_time=impact_t, callback=on_shot_captured)

        # Feed post-impact frames
        for i in range(10, 16):
            t = base_t + i * 0.016
            reading = SensorReading(top_left=30.0, top_right=10.0, bottom_left=30.0, bottom_right=10.0, timestamp=t)
            cop = self.calc.compute(reading)
            self.buf.push(cop, phase='Follow-through')

        self.assertGreater(len(captured_data), 0)
        self.assertTrue(any(f['phase'] == 'Follow-through' for f in captured_data))

if __name__ == '__main__':
    unittest.main()
