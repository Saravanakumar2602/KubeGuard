# Development Roadmap

This roadmap documents the implementation stages of KubeGuard AI.

---

## Completed Phases

### Phase 1: Collector Setup & Prometheus Connectivity (Step 1)
- **Goal**: Make Python communicate with the Prometheus HTTP API.
- **Implemented**: `PrometheusClient` (`prometheus_client.py`) class supporting instant query (`/api/v1/query`).
- **Dependencies**: Added `requests` dependency to `collector-service/requirements.txt`.

### Phase 2: Instant Pod Metrics Collection (Step 2)
- **Goal**: Discover pods and retrieve CPU, Memory, and Restart counts.
- **Implemented**: `Collector` (`collector.py`) class.
- **Verification**: Verified automatic discovery of both `demo-nginx` pods and successful metric matching using pod name as key.

### Phase 3: Historical Queries & Feature Service (Step 3A & 3B)
- **Goal**: Retrieve historical time-series metric data and compute statistical and trend features.
- **Implemented**:
  - Range query (`query_range`) support in `PrometheusClient`.
  - `FeatureService` (`feature_service.py`) class.
  - Linear regression slope trend calculation (`cpu_trend` in units/sec, `memory_trend` in bytes/sec).
  - Dataclasses: `MetricSample`, `PodMetricHistory`, `PodFeatures`.
- **Verification**: Verified trend direction calculations (e.g. positive/negative slopes) and edge-case behaviors (0/1 samples).

---

### Phase 4: ML model integration & Risk Scorer (Steps 4, 5, & 6)
- **Goal**: Implement unsupervised anomaly detection and operational risk evaluations.
- **Implemented**:
  - Unsupervised `IsolationForest` anomaly classifier inside `AnomalyDetector` class.
  - Linear regression trend slope check for memory leaks inside `FeatureService` class.
  - Grade risk levels (LOW, MEDIUM, HIGH) based on operational indicators inside `RuleEngine` class.

### Phase 5: Servings REST APIs & Exporters (Steps 7, 8, 9 & 10)
- **Goal**: Expose evaluations via REST APIs, Dockerize, deploy, and support metrics scraping.
- **Implemented**:
  - FastAPI uvicorn REST controller inside `api.py`.
  - Exporter registries and stale metric purge methods inside `metrics.py`.
  - ServiceMonitor endpoints target configurations.
  - Dockerized container configurations.

### Phase 6: Continuous Background Monitoring (Step 11)
- **Goal**: Run background evaluations without blocking API request lifecycle.
- **Implemented**:
  - Thread-safe background scanner `MonitoringWorker` inside `worker.py` checking namespace pods.

### Phase 7: Prometheus Alerting & Helm Packaging (Steps 12 & 13)
- **Goal**: Setup Kubernetes native alerting and package as an installable Helm chart.
- **Implemented**:
  - `PrometheusRule` configurations triggering critical alerts on thresholds.
  - Reusable Helm Chart packaging namespaces, service monitors, deployment rules, and Grafana ConfigMaps.

