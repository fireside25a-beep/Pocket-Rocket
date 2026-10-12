from __future__ import annotations

import unittest

from neuro_inverse.binary_router import calibrated_centroid
from neuro_inverse.envelope import run_stress_profiles


class SurfaceConnectionTests(unittest.TestCase):
    def test_calibrated_centroid_is_exercised(self) -> None:
        self.assertEqual(calibrated_centroid([b"\x00" * 32, b"\xff" * 32]), b"\xff" * 32)

    def test_envelope_stress_profiles_are_exercised(self) -> None:
        reports = run_stress_profiles()
        self.assertTrue(reports)
        self.assertTrue(all(report.scenario_count == report.outputs for report in reports))


if __name__ == "__main__":
    unittest.main()
