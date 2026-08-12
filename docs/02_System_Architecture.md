# System Architecture

The following diagram shows the high-level architecture of KubeGuard AI components up to Helm Packaging (Step 13):

```mermaid
flowchart TD
    subgraph Kubernetes Cluster
        K8s["☸️ Target Namespace Pods (demo/kubeguard-test)"]
        PromOperator["⚙️ Prometheus Operator"]
        ServiceMonitor["⚙️ ServiceMonitor Target"]
        PromRule["🔔 PrometheusRule Alerting"]
    end

    subgraph Monitoring Stack
        Prometheus["📊 Prometheus Server"]
        Alertmanager["🔔 Alertmanager"]
        Grafana["📈 Grafana Dashboard"]
    end

    subgraph KubeGuard Release
        ConfigMap["⚙️ ConfigMap (PROMETHEUS_URL)"]
        Deployment["🐍 FastAPI Prediction Container"]
        Service["⚙️ ClusterIP Service :8000"]
        Worker["⚙️ Background Monitoring Worker"]
        Exporter["⚙️ Prometheus Exporter (/metrics)"]
    end

    K8s -->|Scrapes Metrics| Prometheus
    Prometheus -->|Historical range queries| Deployment
    Deployment -->|Feature Engineering| Worker
    Worker -->|ML Model & Rule Evaluation| Exporter
    Exporter -->|Exposes Scrape Target| Service
    ServiceMonitor -->|Discovers Endpoint| Service
    Prometheus -->|Scrapes Exporter Endpoint| Service
    PromOperator -->|Deploys and Configures| ServiceMonitor
    PromOperator -->|Deploys and Configures| PromRule
    PromRule -->|Evaluates Risk Alerts| Prometheus
    Prometheus -->|Routes Alerts| Alertmanager
    Grafana -->|Queries Metrics| Prometheus
```

## Architectural Decoupling

- **PrometheusClient**: Holds connection setup, status verification, and raw HTTP query execution.
- **Collector**: Focuses purely on instant cluster states (pod discovery, current metrics, restart counts).
- **Feature Service**: Focuses on historical trends (time-series sample collection, statistical aggregations, regression slope computation).
- **Prediction Orchestration**: Links Feature Service pipelines, Isolation Forest classifiers, and Rule Engine logic into atomic scoring evaluations.
- **Monitoring Worker**: Executes scanning loops in a background thread to decouple FastAPI REST response time from cluster evaluation durations.
- **Prometheus Integration**: Exposes metrics endpoints and triggers rules configurations natively using Operator definitions.
- **Helm Release Packaging**: Standardizes installation using a unified parameter values configuration.

