"""Unit tests for Alertmanager alert correlation and failure resilience."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "../src"))
if src_dir not in sys.path:
    sys.path.append(src_dir)

from incident import Incident, CorrelatedAlert
from incident_store import IncidentStore
from incident_manager import IncidentManager


class TestIncidentAlerts(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_alerts.db")
        self.store = IncidentStore(db_path=self.db_path)
        self.manager = IncidentManager(incident_store=self.store, alertmanager_url="http://mock-alertmanager:9093")

    def tearDown(self):
        self.tmp_dir.cleanup()

    @patch("requests.get")
    def test_correlate_alerts_firing_and_resolution(self, mock_get):
        # Setup active incident in store
        inc = Incident(
            incident_id="demo/pod-1/1000",
            namespace="demo",
            pod="pod-1",
            created_at="2026-08-13T10:00:00Z",
            updated_at="2026-08-13T10:00:00Z",
            status="active",
            risk_level="HIGH",
            risk_score=85,
            recommendation="Investigate memory.",
        )
        self.store.create_incident(inc)

        # Mock Alertmanager returning a firing alert for demo/pod-1
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = [
            {
                "labels": {
                    "alertname": "KubeGuardMemoryGrowth",
                    "severity": "critical",
                    "exported_namespace": "demo",
                    "exported_pod": "pod-1",
                },
                "startsAt": "2026-08-13T10:05:00Z",
            }
        ]
        mock_get.return_value = mock_response

        # Execute correlation
        self.manager.correlate_alerts()

        fetched = self.store.get_incident("demo/pod-1/1000")
        self.assertEqual(len(fetched.alerts), 1)
        self.assertEqual(fetched.alerts[0].alert_name, "KubeGuardMemoryGrowth")
        self.assertIsNone(fetched.alerts[0].resolved_at)

        # Second cycle: Alert clears from Alertmanager
        mock_response.json.return_value = []
        self.manager.correlate_alerts()

        fetched_after = self.store.get_incident("demo/pod-1/1000")
        self.assertEqual(len(fetched_after.alerts), 1)
        self.assertIsNotNone(fetched_after.alerts[0].resolved_at)

    @patch("requests.get")
    def test_alertmanager_unreachable_does_not_fail(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        # Should log warning and exit cleanly without raising exception
        self.manager.correlate_alerts()


if __name__ == "__main__":
    unittest.main()
