# KubeGuard AI — REST API Documentation

The KubeGuard FastAPI application serves prediction endpoints, incident management contexts, model metadata, exporter metrics, and health probes.

---

## 1. System Health & Readiness

### Service Health
- **Endpoint**: `GET /health`
- **Response (`200 OK`)**:
  ```json
  {
    "status": "healthy",
    "worker_running": true,
    "baseline_trained": true,
    "last_successful_monitoring": 1786689500.0,
    "worker_status": "healthy"
  }
  ```

### Readiness Probe
- **Endpoint**: `GET /ready`
- **Response (`200 OK`)**:
  ```json
  {
    "status": "ready",
    "worker_running": true,
    "last_successful_monitoring": 1786689500.0
  }
  ```

---

## 2. Pod Prediction Service

- **Endpoint**: `GET /predict/{namespace}/{pod}`
- **Path Parameters**:
  - `namespace` (string, required): Pod target namespace (e.g. `demo`).
  - `pod` (string, required): Target pod name.
- **Response (`200 OK`)**:
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

---

## 3. Incident Correlation Endpoints

### List Incidents
- **Endpoint**: `GET /incidents?namespace=demo&status=active&limit=50`
- **Query Parameters**:
  - `namespace` (string, optional): Filter by namespace.
  - `status` (string, optional): Filter by `active` or `resolved`.
  - `limit` (integer, optional): Maximum records to return (default: 50).
- **Response (`200 OK`)**:
  ```json
  [
    {
      "incident_id": "demo/pod-1/1786689500",
      "namespace": "demo",
      "pod": "pod-1",
      "status": "active",
      "risk_level": "HIGH",
      "risk_score": 85,
      "created_at": "2026-08-15T09:00:00Z",
      "updated_at": "2026-08-15T09:05:00Z"
    }
  ]
  ```

### Get Incident Detail
- **Endpoint**: `GET /incidents/{incident_id:path}`
- **Response (`200 OK`)**:
  ```json
  {
    "incident_id": "demo/pod-1/1786689500",
    "namespace": "demo",
    "pod": "pod-1",
    "status": "active",
    "risk_level": "HIGH",
    "risk_score": 85,
    "created_at": "2026-08-15T09:00:00Z",
    "updated_at": "2026-08-15T09:05:00Z",
    "signals": [
      {
        "signal_name": "memory_growth",
        "severity": "HIGH",
        "value": "5000 B/s",
        "description": "Memory growth detected.",
        "detected_at": "2026-08-15T09:00:00Z"
      }
    ],
    "timeline": [
      {
        "timestamp": "2026-08-15T09:00:00Z",
        "event_type": "incident_created",
        "description": "Incident created for pod 'pod-1' in namespace 'demo'",
        "severity": "high"
      }
    ],
    "alerts": [],
    "recommendation": "Investigate memory growth."
  }
  ```

---

## 4. Model Metadata Endpoint

- **Endpoint**: `GET /model`
- **Response (`200 OK`)**:
  ```json
  {
    "model_version": 1,
    "model_source": "historical",
    "training_sample_count": 50,
    "trained_at": "2026-08-15T09:00:00Z"
  }
  ```

---

## 5. Exporter Prometheus Metrics

- **Endpoint**: `GET /metrics`
- **Response**: Standard Prometheus exposition format containing `kubeguard_*` self-observability and workload risk gauges.
