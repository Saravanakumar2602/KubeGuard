import os
import sys
import time
import unittest
from unittest.mock import MagicMock

# Resolve paths
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "../src"))
if src_dir not in sys.path:
    sys.path.append(src_dir)

from worker import MonitoringWorker
from metrics import kubeguard_pod_risk_score, kubeguard_pod_anomaly, cleanup_stale_metrics


class TestMonitoringWorker(unittest.TestCase):

    def test_worker_default_configuration(self):
        """Verify default configuration parameters for worker."""
        # Clear environment variables to test defaults
        if "MONITOR_INTERVAL_SECONDS" in os.environ:
            del os.environ["MONITOR_INTERVAL_SECONDS"]
        if "MONITOR_NAMESPACES" in os.environ:
            del os.environ["MONITOR_NAMESPACES"]

        orchestrator = MagicMock()
        worker = MonitoringWorker(orchestrator)
        self.assertEqual(worker.interval, 30.0)
        self.assertEqual(worker.namespaces, ["demo", "kubeguard-test"])


    def test_worker_custom_configuration(self):
        """Verify custom environment configuration parameters."""
        os.environ["MONITOR_INTERVAL_SECONDS"] = "15"
        os.environ["MONITOR_NAMESPACES"] = "demo, kubeguard-test "

        try:
            orchestrator = MagicMock()
            worker = MonitoringWorker(orchestrator)
            self.assertEqual(worker.interval, 15.0)
            self.assertEqual(worker.namespaces, ["demo", "kubeguard-test"])
        finally:
            del os.environ["MONITOR_INTERVAL_SECONDS"]
            del os.environ["MONITOR_NAMESPACES"]

    def test_worker_lifecycle_start_stop(self):
        """Verify worker starts and stops background thread cleanly."""
        orchestrator = MagicMock()
        orchestrator.detector.is_fitted = True
        orchestrator.collector._discover_pods.return_value = []
        
        worker = MonitoringWorker(orchestrator)
        worker.interval = 0.1  # Make it fast for test execution
        
        # Start worker
        worker.start()
        self.assertIsNotNone(worker._thread)
        self.assertTrue(worker._thread.is_alive())
        
        # Stop worker
        worker.stop()
        self.assertIsNone(worker._thread)
        self.assertTrue(worker._stop_event.is_set())


    def test_stale_metrics_cleanup(self):
        """Verify stale metrics cleanup deletes untracked pods from registry."""
        # 1. Populate gauge with normal and stale pods
        kubeguard_pod_risk_score.labels(namespace="demo", pod="active-nginx").set(4.0)
        kubeguard_pod_risk_score.labels(namespace="demo", pod="stale-nginx").set(10.0)
        
        # Verify both exist
        self.assertIn(("demo", "active-nginx"), kubeguard_pod_risk_score._metrics)
        self.assertIn(("demo", "stale-nginx"), kubeguard_pod_risk_score._metrics)

        # 2. Run cleanup with only active pod in list
        active_pods = [("active-nginx", "demo")]
        cleanup_stale_metrics(active_pods)

        # 3. Assert stale pod is removed, active pod remains
        self.assertIn(("demo", "active-nginx"), kubeguard_pod_risk_score._metrics)
        self.assertNotIn(("demo", "stale-nginx"), kubeguard_pod_risk_score._metrics)


if __name__ == "__main__":
    unittest.main()
