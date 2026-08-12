# API Documentation

The FastAPI application exposes prediction services, metrics scraping targets, and system check endpoints.

---

## 1. Get Pod Predictions

Retrieves real-time features processing, anomaly classification, and scaling advice for a specific Kubernetes Pod.

- **Endpoint**: `GET /predict/{namespace}/{pod}`
- **Path Parameters**:
  - `namespace` (string, required): Pod target namespace (e.g. `demo`).
  - `pod` (string, required): Target pod identifier.
- **Example Response (`200 OK`)**:
  ```json
  {
    "pod": "demo-nginx-7cb864b4f9-jvjh8",
    "namespace": "demo",
    "risk_score": 4,
    "risk_level": "LOW",
    "anomaly_detected": false,
    "rules_triggered": [],
    "recommendation": "All systems nominal for pod demo-nginx-7cb864b4f9-jvjh8. No action required."
  }
  ```
- **Error Response (`400 Bad Request`)**:
  ```json
  {
    "detail": "Incomplete observation for pod demo-nginx-7cb864b4f9-jvjh8. Feature index 0 is None. All features must be fully populated."
  }
  ```

---

## 2. Prometheus Exporter Metrics

Provides the current cluster state in standard text formatting for scraping by Prometheus.

- **Endpoint**: `GET /metrics`
- **Output Mappings**:
  - `kubeguard_pod_risk_score`: Current risk score registry Gauge.
  - `kubeguard_pod_anomaly`: Current outlier status Gauge (1 = Anomaly, 0 = Normal).
  - `kubeguard_pod_risk_level`: Multi-label Gauge mapping risk grades (LOW, MEDIUM, HIGH).
  - `kubeguard_pod_cpu_trend`: Evaluated CPU slope value (cores/second).
  - `kubeguard_pod_memory_trend_bytes_per_second`: Evaluated Memory slope value (bytes/second).
  - `kubeguard_pod_restart_count`: Active restart count.

---

## 3. System Healthcheck

FastAPI health verification endpoints.

- **Endpoint**: `GET /health`
- **Response (`200 OK`)**:
  ```json
  {
    "status": "healthy",
    "worker_running": true,
    "baseline_trained": true
  }
  ```
