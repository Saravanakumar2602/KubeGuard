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

---

## 3. Prediction & Scoring Flow
This sequence shows how client API requests or background evaluations process data to grade risk levels.

```mermaid
sequenceDiagram
    participant API as FastAPI /predict
    participant Orch as PredictionOrchestrator
    participant Coll as Collector
    participant FS as FeatureService
    participant AD as AnomalyDetector
    participant RE as RuleEngine

    API->>Orch: predict_pod(namespace, pod)
    Orch->>Coll: collect(namespace)
    Coll-->>Orch: PodMetrics
    Orch->>FS: calculate_features(history, restarts)
    FS-->>Orch: PodFeatures
    Orch->>AD: predict(PodFeatures)
    AD-->>Orch: anomaly_detected (True/False)
    Orch->>RE: evaluate(PodFeatures, anomaly_detected)
    RE-->>Orch: RiskResult (Score, Level, Recommendations)
    Orch-->>API: RiskResult JSON
```

---

## 4. Background Monitoring & Alerting Flow
The continuously running worker loop fetches cluster metrics, updates exporter Gauges, and fires alerts.

```mermaid
sequenceDiagram
    participant Worker as MonitoringWorker
    participant Orch as PredictionOrchestrator
    participant Registry as Prometheus Exporter
    participant Prometheus as Prometheus Server
    participant Alert as Alertmanager

    loop Every 30 seconds
        Worker->>Worker: Discover active pods in namespaces
        Worker->>Orch: predict_pod(namespace, pod)
        Orch-->>Worker: RiskResult + PodFeatures
        Worker->>Registry: update_metrics(namespace, pod, result, features)
        Worker->>Registry: cleanup_stale_metrics(active_pods)
    end

    Prometheus->>Registry: GET /metrics (Every 15 seconds)
    Registry-->>Prometheus: Gauges text formatting

    Prometheus->>Prometheus: Evaluates rules (kubeguard_pod_risk_score >= 60)
    Note over Prometheus: Active alert transitions to PENDING then FIRING after 2m
    Prometheus->>Alert: POST /api/v2/alerts (Firing Alerts)
```

```
