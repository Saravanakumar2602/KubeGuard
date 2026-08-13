# KubeGuard AI — Historical Feature Store & Model Lifecycle Architecture

This document describes the historical feature store and model lifecycle implementation introduced in Step 16 of KubeGuard AI.

---

## 1. Overview & Problem Statement

Prior to Step 16, KubeGuard initialized its Isolation Forest anomaly detector by gathering a single baseline snapshot of normal metrics from the `demo` namespace and generating 20 synthetic observations using Gaussian perturbation noise. While effective for initial prototyping, synthetic bootstrap data does not reflect long-term workload trends or diurnal resource usage patterns.

Step 16 introduces **telemetry persistence** and **historical model training**:
- Workload feature vectors computed during routine monitoring scans are automatically stored in an embedded SQLite feature store (`/data/kubeguard.db`).
- Once stored observations reach `MIN_TRAINING_SAMPLES` (default: 50), KubeGuard transitions from a synthetic **Bootstrap Model** to a **Historical Model** trained on real cluster behavior.
- Trained model artifacts are serialized using `joblib` (`/data/kubeguard-isolation-forest.joblib`) alongside JSON metadata tracking model version, source, training sample count, and timestamps.
- Data persists across pod restarts via a Kubernetes `PersistentVolumeClaim` (1Gi) mounted at `/data`.

---

## 2. System Architecture & Data Flow

```
Prometheus Time Series
       │
       ▼
Collector & Feature Service
       │
       ▼
Feature Store (SQLite: /data/kubeguard.db)
       │
       ├── Observations < MIN_TRAINING_SAMPLES ──► Bootstrap Fallback Model (synthetic perturbation)
       │
       └── Observations >= MIN_TRAINING_SAMPLES ─► Historical Model Training (joblib: /data/kubeguard-isolation-forest.joblib)
                                                           │
                                                           ▼
                                               Prediction & Risk Evaluation
                                                           │
                                                           ▼
                                                 Prometheus Exporter & GET /model
```

---

## 3. Feature Store Architecture & SQLite Schema

The `FeatureStore` class (`prediction-service/src/feature_store.py`) provides an abstracted repository layer wrapping an embedded SQLite database.

### Database Location
- **Container / Production Path**: `/data/kubeguard.db`
- **Environment Variable**: `FEATURE_STORE_PATH`
- **Local Development Default**: `./data/kubeguard.db`

### Table Schema: `feature_observations`

```sql
CREATE TABLE IF NOT EXISTS feature_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    namespace TEXT NOT NULL,
    pod TEXT NOT NULL,
    cpu_current REAL,
    cpu_average REAL,
    cpu_max REAL,
    cpu_min REAL,
    cpu_trend REAL,
    memory_current REAL,
    memory_average REAL,
    memory_max REAL,
    memory_min REAL,
    memory_trend REAL,
    restart_count INTEGER
);

CREATE INDEX IF NOT EXISTS idx_ns_pod_ts ON feature_observations (namespace, pod, timestamp);
CREATE INDEX IF NOT EXISTS idx_ts ON feature_observations (timestamp);
```

### Deduplication Strategy
During monitoring scans, `save_feature()` checks if an observation for the same `(namespace, pod)` exists within a 5-second window to prevent duplicate records from rapid scan ticks.

---

## 4. Feature Retention Policy

- **Environment Variable**: `FEATURE_RETENTION_DAYS` (default: `7`)
- **Cleanup Trigger**: The monitoring worker periodically executes `FeatureStore.delete_old_features(retention_days)` (once every 6 hours).
- **Behavior**: Purges records where `timestamp < (now - retention_days * 86400)`.

---

## 5. Model Serialization & Metadata Tracking

The `ModelStore` class (`prediction-service/src/model_store.py`) handles model artifact persistence using `joblib`.

### File Location
- **Container / Production Path**: `/data/kubeguard-isolation-forest.joblib`
- **Environment Variable**: `MODEL_PATH`

### Model Metadata Structure

When a model is serialized, metadata is embedded alongside the scikit-learn pipeline:

```json
{
  "model_version": 1,
  "trained_at": "2026-08-13T09:08:53Z",
  "trained_at_timestamp": 1786612133.45,
  "training_sample_count": 16,
  "model_source": "historical",
  "contamination": 0.1,
  "random_state": 42,
  "feature_names": [
    "cpu_current", "cpu_average", "cpu_max", "cpu_min", "cpu_trend",
    "memory_current", "memory_average", "memory_max", "memory_min", "memory_trend",
    "restart_count"
  ]
}
```

---

## 6. Training & Retraining Lifecycle

1. **Startup Check**:
   - When FastAPI starts, `initialize_model()` checks if `/data/kubeguard-isolation-forest.joblib` exists.
   - If present and valid, the persisted model artifact is loaded immediately (`model_source: historical` or `model_source: bootstrap`).
   - If missing, it checks `count_features()` in SQLite.
   - If `count_features() >= MIN_TRAINING_SAMPLES`, it trains a new **Historical Model** on stored feature vectors.
   - If `count_features() < MIN_TRAINING_SAMPLES`, it falls back to the **Bootstrap Model** (synthetic baseline perturbation).

2. **Automated Retraining**:
   - **Environment Variable**: `MODEL_RETRAIN_INTERVAL_SECONDS` (default: `3600`)
   - The monitoring worker checks if the retraining interval has elapsed.
   - If `count_features() >= MIN_TRAINING_SAMPLES`, it trains a new model generation, increments `model_version`, and atomically overwrites the joblib artifact on disk.

---

## 7. Kubernetes Storage & PVC

A 1Gi `PersistentVolumeClaim` (`kubeguard-pvc`) is bound and mounted to `/data` in the KubeGuard deployment:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: kubeguard-pvc
  namespace: kubeguard
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
```

### Pod Restart Persistence Verification
During Step 16 testing, `kubectl rollout restart deployment/kubeguard` was executed. Logs verified:

```text
INFO:kubeguard-model-store:Loaded persisted model from /data/kubeguard-isolation-forest.joblib (version=1, source=historical)
INFO:kubeguard-api:Loaded persisted Isolation Forest model (version=1, source=historical, samples=16)
INFO:kubeguard-worker:Monitoring worker started. Interval: 30.0s, Namespaces: ['demo', 'kubeguard-test']
```

---

## 8. API & CLI Observability

### `GET /model` Endpoint
Returns the active model metadata:

```json
{
  "source": "historical",
  "version": 1,
  "trained_at": "2026-08-13T09:08:53Z",
  "training_samples": 16,
  "feature_count": 11
}
```

### `kubeguard status` Output
The CLI queries `/model` and displays model provenance:

```text
KubeGuard Status
────────────────────────────────────────
  Installation  : Installed
  Namespace     : kubeguard
  Release       : kubeguard
  Deployment    : Ready (1/1)
  Monitoring    : Running
  Prometheus    : Connected
  Alertmanager  : Available
  Model Source  : historical
  Model Version : v1
  Service       : kubeguard:8000
```

---

## 9. Future Production Migration Path

The SQLite + `joblib` architecture is designed as a clean, beginner-friendly prototype storage layer. For large-scale multi-cluster production environments:

1. **Database Layer**: Replace `FeatureStore` SQLite connection with `psycopg2` / PostgreSQL to allow multiple read/write replicas across nodes.
2. **Model Registry**: Replace local `joblib` file persistence with MLflow or AWS S3 / MinIO object storage.
3. **Async Training Worker**: Move model training to a Celery or Ray task queue separate from the API thread.
