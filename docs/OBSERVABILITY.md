# KubeGuard AI — Configuration & Observability Architecture

This document describes the platform self-observability, central configuration system, structured logging, internal Prometheus metrics, worker health semantics, and operational alerting introduced in Step 17 of KubeGuard AI.

---

## 1. Observability Architecture Overview

"KubeGuard monitors Kubernetes workloads AND exposes operational telemetry describing KubeGuard's own health."

```
┌────────────────────────────────────────────────────────────────────────┐
│                        KubeGuard AI Platform                           │
│                                                                        │
│  ┌────────────────┐      ┌────────────────────┐      ┌──────────────┐  │
│  │   config.py    │ ───► │ logging_config.py  │ ───► │ stdout (JSON)│  │
│  └────────────────┘      └────────────────────┘      └──────────────┘  │
│          │                                                             │
│          ▼                                                             │
│  ┌────────────────┐      ┌────────────────────┐      ┌──────────────┐  │
│  │ Background     │ ───► │ Self-Metrics       │ ───► │ /metrics     │  │
│  │ Worker Loop    │      │ (metrics.py)       │      └──────────────┘  │
│  └────────────────┘      └────────────────────┘             │          │
│          │                         │                        ▼          │
│          ▼                         ▼                 ┌──────────────┐  │
│  ┌────────────────┐      ┌────────────────────┐      │ Prometheus / │  │
│  │ Feature/Model  │      │ Health & Readiness │ ───► │ Grafana /    │  │
│  │ Store          │      │ (/health, /ready)  │      │ CLI / Alerts │  │
│  └────────────────┘      └────────────────────┘      └──────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Central Configuration System (`config.py`)

All application settings are centralized in `KubeGuardConfig` (`prediction-service/src/config.py`). Configuration values are populated from environment variables with strict type conversion and range validation.

| Environment Variable | Default Value | Description |
|----------------------|---------------|-------------|
| `PROMETHEUS_URL` | `http://localhost:9090` | Internal Prometheus service URL for scraping cluster metrics |
| `MONITOR_NAMESPACES` | `demo,kubeguard-test` | Comma-separated list of target namespaces to monitor |
| `MONITOR_INTERVAL_SECONDS` | `30` | Periodic background worker scan interval |
| `FEATURE_STORE_PATH` | `/data/kubeguard.db` | Embedded SQLite database file path for telemetry observations |
| `FEATURE_RETENTION_DAYS` | `7` | Retention window for feature history purging |
| `MODEL_PATH` | `/data/kubeguard-isolation-forest.joblib` | Persisted Isolation Forest model file path |
| `MIN_TRAINING_SAMPLES` | `50` | Minimum SQLite observation count before training historical model |
| `MODEL_RETRAIN_INTERVAL_SECONDS` | `3600` | Automated model retraining check interval |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `LOG_FORMAT` | `text` | Log format output (`text` or `json`) |
| `WORKER_HEALTH_TIMEOUT_SECONDS` | `90` | Inactivity threshold before worker health transitions to `degraded` |

### Startup Summary Log
On application startup, KubeGuard prints a sanitized configuration summary:

```text
2026-08-13 09:34:00 [INFO] kubeguard-config: KubeGuard Configuration Summary:
2026-08-13 09:34:00 [INFO] kubeguard-config:   Prometheus URL           : http://kube-prometheus-stack-prometheus.monitoring.svc:9090
2026-08-13 09:34:00 [INFO] kubeguard-config:   Monitoring Interval      : 30.0s
2026-08-13 09:34:00 [INFO] kubeguard-config:   Monitoring Namespaces    : demo,kubeguard-test
2026-08-13 09:34:00 [INFO] kubeguard-config:   Feature Store Path       : /data/kubeguard.db
2026-08-13 09:34:00 [INFO] kubeguard-config:   Feature Retention Days   : 7 days
2026-08-13 09:34:00 [INFO] kubeguard-config:   Model Path               : /data/kubeguard-isolation-forest.joblib
2026-08-13 09:34:00 [INFO] kubeguard-config:   Minimum Training Samples : 50
2026-08-13 09:34:00 [INFO] kubeguard-config:   Model Retrain Interval   : 3600.0s
2026-08-13 09:34:00 [INFO] kubeguard-config:   Log Level / Format       : INFO / text
2026-08-13 09:34:00 [INFO] kubeguard-config:   Worker Health Timeout    : 90.0s
```

---

## 3. Structured Text & JSON Logging (`logging_config.py`)

KubeGuard supports both human-readable text logs and machine-parsable JSON lines via `LOG_FORMAT`.

### JSON Line Output Example (`LOG_FORMAT=json`)
```json
{
  "timestamp": "2026-08-13T09:34:05Z",
  "level": "INFO",
  "logger": "kubeguard-worker",
  "message": "Metrics updated successfully for pod 'demo-nginx-6b89dd5974-6v2g5' in 'demo'",
  "namespace": "demo",
  "pod": "demo-nginx-6b89dd5974-6v2g5"
}
```

---

## 4. Internal Prometheus Self-Metrics Taxonomy

KubeGuard exports operational self-metrics alongside workload risk gauges under the `kubeguard_*` namespace at `GET /metrics`.

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `kubeguard_monitoring_cycles_total` | Counter | None | Total monitoring cycles executed |
| `kubeguard_monitoring_cycle_failures_total` | Counter | None | Total unhandled monitoring cycle failures |
| `kubeguard_monitoring_cycle_duration_seconds` | Histogram | None | Execution latency per monitoring cycle |
| `kubeguard_pod_predictions_total` | Counter | `namespace`, `result` | Pod predictions evaluated (`success` / `failure`) |
| `kubeguard_prediction_duration_seconds` | Histogram | `namespace` | Individual pod prediction execution duration |
| `kubeguard_feature_store_observations_total` | Counter | None | Feature observations saved to SQLite |
| `kubeguard_feature_store_errors_total` | Counter | None | SQLite database error count |
| `kubeguard_feature_store_records` | Gauge | None | Total stored feature observations in SQLite |
| `kubeguard_model_training_total` | Counter | `source` | Model training count (`bootstrap` / `historical`) |
| `kubeguard_model_training_duration_seconds` | Histogram | `source` | Model fitting duration |
| `kubeguard_model_load_total` | Counter | `result` | Model load attempts (`success` / `missing` / `failure`) |
| `kubeguard_model_info` | Gauge | `source`, `version` | Active Isolation Forest model provenance (value = 1) |
| `kubeguard_worker_last_success_timestamp` | Gauge | None | Unix timestamp of last successful monitoring cycle |
| `kubeguard_worker_last_cycle_timestamp` | Gauge | None | Unix timestamp of most recent monitoring cycle |
| `kubeguard_worker_pods_evaluated` | Gauge | None | Pod count evaluated in most recent cycle |
| `kubeguard_worker_healthy` | Gauge | None | 1 = Healthy, 0 = Unhealthy |
| `kubeguard_config_info` | Gauge | `monitor_interval_seconds`, `retention_days`, `min_training_samples`, `retrain_interval_seconds` | Configuration metadata gauge (value = 1) |

---

## 5. Worker Health & Endpoint Semantics

### Worker Health Evaluation
- **Healthy (`kubeguard_worker_healthy = 1`)**: When `(now - last_success_timestamp) <= WORKER_HEALTH_TIMEOUT_SECONDS` (or initial startup).
- **Degraded (`kubeguard_worker_healthy = 0`)**: When background scanning stops or takes longer than `WORKER_HEALTH_TIMEOUT_SECONDS` (default: 90s).

### HTTP Endpoint Contracts
- **`GET /health`**: Returns HTTP 200 with service health, worker status, model source, and version.
  ```json
  {
    "status": "healthy",
    "worker": "healthy",
    "model_source": "historical",
    "model_version": 1
  }
  ```
- **`GET /ready`**: Liveness/Readiness probe endpoint. Returns HTTP 200 (`{"status": "ready"}`) when FastAPI is initialized and background worker thread is active. Returns HTTP 530 if worker thread terminates.
- **`GET /metrics`**: Prometheus metrics scrape endpoint.

---

## 6. Operational Self-Alerting Rules

Three operational PrometheusRules monitor KubeGuard itself:

1. **`KubeGuardWorkerDown`** (Critical): Triggers when `kubeguard_worker_healthy == 0` for 2 minutes.
2. **`KubeGuardMonitoringFailures`** (Warning): Triggers when `increase(kubeguard_monitoring_cycle_failures_total[5m]) > 2` for 2 minutes.
3. **`KubeGuardPredictionFailures`** (Warning): Triggers when `increase(kubeguard_pod_predictions_total{result="failure"}[5m]) > 5` for 2 minutes.

---

## 7. CLI Status & Grafana Observability

### CLI Inspection (`kubeguard status`)
```text
KubeGuard Status
----------------------------------------
  Installation    : Installed
  Namespace       : kubeguard
  Release         : kubeguard
  Deployment      : Ready (1/1)
  Monitoring      : Running
  Worker Health   : Healthy
  Last Cycle      : 12s ago
  Last Success    : 12s ago
  Prometheus      : Connected
  Alertmanager    : Available
  Model Source    : historical
  Model Version   : v1
  Feature Records : 124
  Service         : kubeguard:8000
```

### Grafana System Health Dashboard Section
The Grafana dashboard (`kubernetes/grafana/dashboard.json`) includes a dedicated **KubeGuard System Health** row with stat gauges for Worker Health, Last Cycle Time, Feature Records, Active Model Info, and timeseries charts for Cycle Rates, Durations, and Prediction Failures.
