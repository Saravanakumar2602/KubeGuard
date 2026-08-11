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

## Upcoming Phases

- **Phase 4**: ML Model Integration (Isolation Forest for CPU anomaly detection, Linear Regression slope classification for memory leak predictions).
- **Phase 5**: Serving & REST Endpoint (FastAPI server implementation).
- **Phase 6**: Feature Store & Database Integration (PostgreSQL table setup for persistent caching).
- **Phase 7**: Grafana Dashboards, Dockerization, and Helm Deployments.
