"""Unit tests for IncidentManager lifecycle, state transitions, timeline generation, and grace period resolution."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "../src"))
feature_src = os.path.abspath(os.path.join(current_dir, "../../feature-service/src"))

if src_dir not in sys.path:
    sys.path.append(src_dir)
if feature_src not in sys.path:
    sys.path.append(feature_src)

from feature_service import PodFeatures
from anomaly_detector import AnomalyResult
from rule_engine import RiskResult
from incident_store import IncidentStore
from incident_manager import IncidentManager


class TestIncidentManager(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_manager.db")
        self.store = IncidentStore(db_path=self.db_path)
        self.manager = IncidentManager(
            incident_store=self.store,
            resolution_grace_seconds=1.0,  # 1 second grace period for fast testing
            retention_days=30,
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_healthy_pod_produces_no_incident(self):
        f = PodFeatures("healthy-pod", "demo", 0.01, 0.01, 0.01, 0.01, 0.0, 1e7, 1e7, 1e7, 1e7, 0.0, 0)
        a = AnomalyResult("healthy-pod", "demo", is_anomaly=False, score=-0.45)
        r = RiskResult("healthy-pod", "demo", "LOW", 0, [], "Normal")

        inc = self.manager.process_assessment(f, a, r)
        self.assertIsNone(inc)
        self.assertEqual(len(self.store.get_incidents()), 0)

    def test_high_risk_creates_incident(self):
        f = PodFeatures("stress-pod", "kubeguard-test", 0.1, 0.05, 0.1, 0.01, 0.0005, 2e7, 1.5e7, 2e7, 1e7, 5000.0, 0)
        a = AnomalyResult("stress-pod", "kubeguard-test", is_anomaly=True, score=-0.65)
        r = RiskResult("stress-pod", "kubeguard-test", "HIGH", 85, ["ML anomaly", "Memory growth"], "Investigate leakage.")

        inc = self.manager.process_assessment(f, a, r)
        self.assertIsNotNone(inc)
        self.assertEqual(inc.risk_level, "HIGH")
        self.assertEqual(inc.status, "active")
        self.assertGreaterEqual(len(inc.signals), 2)
        self.assertGreaterEqual(len(inc.timeline), 2)

    def test_repeated_high_risk_updates_same_incident(self):
        f = PodFeatures("stress-pod", "kubeguard-test", 0.1, 0.05, 0.1, 0.01, 0.0005, 2e7, 1.5e7, 2e7, 1e7, 5000.0, 0)
        a = AnomalyResult("stress-pod", "kubeguard-test", is_anomaly=True, score=-0.65)
        r = RiskResult("stress-pod", "kubeguard-test", "HIGH", 85, ["ML anomaly", "Memory growth"], "Investigate leakage.")

        inc1 = self.manager.process_assessment(f, a, r)
        inc2 = self.manager.process_assessment(f, a, r)

        # Must be the exact same incident ID
        self.assertEqual(inc1.incident_id, inc2.incident_id)
        active_list = self.store.get_incidents(status="active")
        self.assertEqual(len(active_list), 1)

    def test_resolution_grace_period(self):
        f_bad = PodFeatures("stress-pod", "kubeguard-test", 0.1, 0.05, 0.1, 0.01, 0.0005, 2e7, 1.5e7, 2e7, 1e7, 5000.0, 0)
        a_bad = AnomalyResult("stress-pod", "kubeguard-test", is_anomaly=True, score=-0.65)
        r_bad = RiskResult("stress-pod", "kubeguard-test", "HIGH", 85, ["ML anomaly"], "Investigate.")

        inc1 = self.manager.process_assessment(f_bad, a_bad, r_bad)
        self.assertEqual(inc1.status, "active")

        # Now pod returns to LOW risk
        f_good = PodFeatures("stress-pod", "kubeguard-test", 0.01, 0.01, 0.01, 0.01, 0.0, 1e7, 1e7, 1e7, 1e7, 0.0, 0)
        a_good = AnomalyResult("stress-pod", "kubeguard-test", is_anomaly=False, score=-0.45)
        r_good = RiskResult("stress-pod", "kubeguard-test", "LOW", 0, [], "Normal")

        # Immediate evaluation stays active due to grace period
        inc_grace = self.manager.process_assessment(f_good, a_good, r_good)
        self.assertEqual(inc_grace.status, "active")

        # Sleep past grace period (1.1s > 1.0s grace)
        time.sleep(1.1)
        inc_resolved = self.manager.process_assessment(f_good, a_good, r_good)
        self.assertEqual(inc_resolved.status, "resolved")


if __name__ == "__main__":
    unittest.main()
