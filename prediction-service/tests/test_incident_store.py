"""Unit tests for SQLite-backed IncidentStore repository."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "../src"))
if src_dir not in sys.path:
    sys.path.append(src_dir)

from incident import Incident, Signal, TimelineEvent, CorrelatedAlert
from incident_store import IncidentStore


class TestIncidentStore(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_incidents.db")
        self.store = IncidentStore(db_path=self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_create_and_get_incident(self):
        inc = Incident(
            incident_id="demo/pod-1/1000",
            namespace="demo",
            pod="pod-1",
            created_at="2026-08-13T10:00:00Z",
            updated_at="2026-08-13T10:00:00Z",
            status="active",
            risk_level="HIGH",
            risk_score=85,
            recommendation="Investigate memory leakage.",
            signals=[
                Signal("memory_growth", "HIGH", "5000 B/s", "Memory growth detected.", "2026-08-13T10:00:00Z")
            ],
            timeline=[
                TimelineEvent("2026-08-13T10:00:00Z", "incident_created", "Incident created", "high")
            ],
            alerts=[
                CorrelatedAlert("KubeGuardMemoryGrowth", "critical", "2026-08-13T10:00:00Z")
            ],
        )

        saved = self.store.create_incident(inc)
        self.assertEqual(saved.incident_id, "demo/pod-1/1000")

        fetched = self.store.get_incident("demo/pod-1/1000")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.pod, "pod-1")
        self.assertEqual(fetched.risk_score, 85)
        self.assertEqual(len(fetched.signals), 1)
        self.assertEqual(len(fetched.timeline), 1)
        self.assertEqual(len(fetched.alerts), 1)

    def test_get_active_incident_for_pod(self):
        inc = Incident(
            incident_id="demo/pod-1/1000",
            namespace="demo",
            pod="pod-1",
            created_at="2026-08-13T10:00:00Z",
            updated_at="2026-08-13T10:00:00Z",
            status="active",
            risk_level="HIGH",
            risk_score=85,
            recommendation="Investigate memory leakage.",
        )
        self.store.create_incident(inc)

        active = self.store.get_active_incident_for_pod("demo", "pod-1")
        self.assertIsNotNone(active)
        self.assertEqual(active.incident_id, "demo/pod-1/1000")

        no_active = self.store.get_active_incident_for_pod("demo", "unknown-pod")
        self.assertIsNone(no_active)

    def test_update_and_resolve_incident(self):
        inc = Incident(
            incident_id="demo/pod-1/1000",
            namespace="demo",
            pod="pod-1",
            created_at="2026-08-13T10:00:00Z",
            updated_at="2026-08-13T10:00:00Z",
            status="active",
            risk_level="MEDIUM",
            risk_score=40,
            recommendation="Monitor CPU.",
        )
        self.store.create_incident(inc)

        # Update
        inc.risk_level = "HIGH"
        inc.risk_score = 75
        self.store.update_incident(inc)

        fetched = self.store.get_incident("demo/pod-1/1000")
        self.assertEqual(fetched.risk_level, "HIGH")
        self.assertEqual(fetched.risk_score, 75)

        # Resolve
        resolved = self.store.resolve_incident("demo/pod-1/1000")
        self.assertTrue(resolved)

        fetched_res = self.store.get_incident("demo/pod-1/1000")
        self.assertEqual(fetched_res.status, "resolved")
        self.assertIsNone(self.store.get_active_incident_for_pod("demo", "pod-1"))

    def test_delete_old_resolved_incidents(self):
        old_time = time.time() - (40 * 86400)
        inc_old = Incident(
            incident_id="demo/pod-old/100",
            namespace="demo",
            pod="pod-old",
            created_at="2026-07-01T00:00:00Z",
            updated_at="2026-07-01T00:00:00Z",
            status="resolved",
            risk_level="LOW",
            risk_score=10,
            recommendation="Normal",
        )
        self.store.create_incident(inc_old)
        # Force updated_at timestamp in SQLite
        with self.store._connect() as conn:
            conn.cursor().execute("UPDATE incidents SET updated_at = ? WHERE incident_id = ?", (old_time, "demo/pod-old/100"))
            conn.commit()

        inc_active = Incident(
            incident_id="demo/pod-active/200",
            namespace="demo",
            pod="pod-active",
            created_at="2026-08-13T10:00:00Z",
            updated_at="2026-08-13T10:00:00Z",
            status="active",
            risk_level="HIGH",
            risk_score=80,
            recommendation="High risk",
        )
        self.store.create_incident(inc_active)

        deleted = self.store.delete_old_resolved_incidents(retention_days=30)
        self.assertEqual(deleted, 1)

        self.assertIsNone(self.store.get_incident("demo/pod-old/100"))
        self.assertIsNotNone(self.store.get_incident("demo/pod-active/200"))


if __name__ == "__main__":
    unittest.main()
