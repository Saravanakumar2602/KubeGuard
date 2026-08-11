# System Architecture

The following diagram shows the high-level architecture of the components implemented so far:

```mermaid
flowchart TD
    K8s["☸️ Kubernetes Cluster (Pods)"]
    Prom["📊 Prometheus"]
    Client["🐍 PrometheusClient"]
    Col["⚙️ Collector"]
    FS["⚙️ Feature Service"]
    Output1["📦 Structured PodMetrics"]
    Output2["📦 Structured PodFeatures"]

    K8s -->|Scrapes Metrics| Prom
    Prom -->|HTTP API /api/v1/query| Client
    Prom -->|HTTP API /api/v1/query_range| Client
    Client -->|Raw Metrics JSON| Col
    Client -->|Raw Time-Series JSON| FS
    Col -->|Discovers & Matches| Output1
    FS -->|Parses & Computes Trends| Output2
```

## Architectural Decoupling

- **PrometheusClient**: Holds connection setup, status verification, and raw HTTP query execution.
- **Collector**: Focuses purely on instant cluster states (pod discovery, current metrics, restart counts).
- **Feature Service**: Focuses on historical trends (time-series sample collection, statistical aggregations, regression slope computation).
