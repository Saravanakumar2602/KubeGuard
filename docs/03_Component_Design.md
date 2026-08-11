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
