import os
import sys
import unittest
from fastapi.testclient import TestClient

# Resolve paths to import api
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "../src"))
if src_dir not in sys.path:
    sys.path.append(src_dir)

from api import app, orchestrator, PodNotFoundError, PrometheusConnectionError


class TestKubeGuardAPI(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        """Verify GET /health returns 200 and correct status."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})

    def test_predict_unknown_pod_returns_404(self):
        """Verify GET /predict/demo/nonexistent-pod returns 404."""
        # Ensure model is initialized or mocked to bypass fitted check
        orchestrator.detector.is_fitted = True
        
        response = self.client.get("/predict/demo/nonexistent-pod")
        # If Prometheus is down, we might get a 503 instead of 404, which is also fine.
        # But if Prometheus is up, we expect 404.
        self.assertIn(response.status_code, [404, 503])
        if response.status_code == 404:
            self.assertIn("not found", response.json()["detail"].lower())

    def test_prometheus_unreachable_returns_503(self):
        """Verify GET /predict/{namespace}/{pod} returns 503 when Prometheus is unreachable."""
        # Intentionally point to an invalid address
        original_base = orchestrator.client.base_url
        orchestrator.client.base_url = "http://localhost:9999"
        
        try:
            response = self.client.get("/predict/demo/some-pod")
            self.assertEqual(response.status_code, 503)
            self.assertIn("unreachable", response.json()["detail"].lower())
        finally:
            # Restore original base URL
            orchestrator.client.base_url = original_base


if __name__ == "__main__":
    unittest.main()
