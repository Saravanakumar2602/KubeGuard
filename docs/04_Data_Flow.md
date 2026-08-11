# Data Flow

The following describes how metrics transit and transform inside KubeGuard AI:

---

## 1. Instant Metric Collection Flow
This flow is run periodically to check the immediate health of the cluster.

```mermaid
sequenceDiagram
    participant K8s as Kubernetes API
    participant Prom as Prometheus
    participant Col as Collector
    participant PC as PrometheusClient

    Col->>PC: collect(namespace="demo")
    PC->>Prom: GET /api/v1/query?query=kube_pod_info{namespace="demo"}
    Prom-->>PC: Pod List JSON
    PC->>Prom: GET /api/v1/query?query=sum(rate(container_cpu_usage_seconds_total...))
    Prom-->>PC: CPU usage per pod
    PC->>Prom: GET /api/v1/query?query=sum(container_memory_working_set_bytes...)
    Prom-->>PC: Memory usage per pod
    PC->>Prom: GET /api/v1/query?query=sum(kube_pod_container_status_restarts_total...)
    Prom-->>PC: Restart counts per pod
    Col-->>Col: Match all metrics using pod name as key
    Col-->>Col: Construct list of PodMetrics objects
```

---

## 2. Feature Calculation Flow
This flow runs to gather historical metrics for training or live machine learning model evaluation.

```mermaid
sequenceDiagram
    participant Prom as Prometheus
    participant FS as FeatureService
    participant PC as PrometheusClient

    FS->>PC: get_cpu_history(start, end, step)
    PC->>Prom: GET /api/v1/query_range?query=sum(rate(container_cpu_usage_seconds_total...))
    Prom-->>PC: CPU time-series matrix JSON
    FS->>PC: get_memory_history(start, end, step)
    PC->>Prom: GET /api/v1/query_range?query=sum(container_memory_working_set_bytes...)
    Prom-->>PC: Memory time-series matrix JSON
    FS->>FS: calculate_features(cpu_history, memory_history, restart_count)
    FS-->>FS: Calculate Min, Max, Average for CPU & Memory
    FS-->>FS: Compute regression slope (CPU: units/sec, Memory: bytes/sec)
    FS-->>FS: Construct list of PodFeatures objects
```
