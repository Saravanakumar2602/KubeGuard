# Component Design

This document details the classes, dataclasses, and functions designed for KubeGuard AI.

---

## Dataclasses

### `PodMetrics`
```python
@dataclass
class PodMetrics:
    pod: str
    namespace: str
    cpu_usage: float
    memory_usage: float
    restart_count: int
```

### `MetricSample`
```python
@dataclass
class MetricSample:
    timestamp: float
    value: float
```

### `PodMetricHistory`
```python
@dataclass
class PodMetricHistory:
    pod: str
    metric: str
    samples: List[MetricSample]
```

### `PodFeatures`
```python
@dataclass
class PodFeatures:
    pod: str
    namespace: str
    cpu_current: float | None
    cpu_average: float | None
    cpu_max: float | None
    cpu_min: float | None
    cpu_trend: float | None  # CPU units/sec
    memory_current: float | None
    memory_average: float | None
    memory_max: float | None
    memory_min: float | None
    memory_trend: float | None  # Bytes/sec
    restart_count: int
```

---

## Classes

### `PrometheusClient`
Handles standard client integration to the Prometheus HTTP Server.
- `query(promql: str) -> dict`: Queries Instant API (`/api/v1/query`).
- `query_range(promql: str, start: float, end: float, step: int) -> dict`: Queries Range API (`/api/v1/query_range`).

### `Collector`
Discovers and matches current pod performance stats.
- `collect(namespace: str) -> List[PodMetrics]`: Executes discovery and metrics queries, assembling them into pod metrics lists.

### `FeatureService`
Aggregates historical time-series metrics.
- `get_cpu_history(...) -> List[PodMetricHistory]`
- `get_memory_history(...) -> List[PodMetricHistory]`
- `calculate_features(...) -> List[PodFeatures]`: Transforms CPU/Memory histories and restarts into statistical and slope-based trend features.

### `RiskResult` (Pydantic Model)
Represents the evaluated health status of a Kubernetes Pod.
```python
class RiskResult(BaseModel):
    pod: str
    namespace: str
    risk_score: int
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    anomaly_detected: bool
    rules_triggered: List[str]
    recommendation: str
```

### `AnomalyDetector`
Manages the IsolationForest model baseline training and inference.
- `train_baseline(normal_observations: List[PodFeatures])`: Trains the model using synthetic normal baseline behaviors.
- `predict(features: PodFeatures) -> bool`: Infers if the pod features are anomalous.

### `RuleEngine`
Computes deterministic operational scores and scaling recommendations.
- `evaluate(features: PodFeatures, anomaly_detected: bool) -> RiskResult`: Applies checks on trend slopes, anomalies, and restart thresholds.

### `PredictionOrchestrator`
Orchestrates prediction lifecycle pipelines.
- `predict_pod(namespace: str, pod: str) -> RiskResult`: Coordinates collecting, parsing features, predicting anomaly state, and scoring rules.

### `MonitoringWorker`
Daemon executing background scanning loops.
- `start()`: Launches thread running scan cycles.
- `stop()`: Shuts down background threads cleanly.
- `_run_loop()`: Periodically calls `PredictionOrchestrator` for all active pods in target namespaces.

### `metrics` Module
Handles Prometheus registry formatting and updates.
- `update_metrics(namespace: str, pod: str, result: RiskResult, features: PodFeatures)`: Writes scores, anomaly status, and trends to Gauges.
- `cleanup_stale_metrics(active_pods: Set[Tuple[str, str]])`: Clears Gauges for deleted pods.

