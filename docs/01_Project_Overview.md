# Project Overview

KubeGuard AI is an installable Kubernetes plugin that adds AI-powered health monitoring and predictive recommendations on top of Kubernetes, Prometheus, and Grafana.

## Core Services Completed

### 1. Collector Service (`collector-service`)
Responsible for communicating with Prometheus and gathering real-time telemetry from Kubernetes pods.
- **PrometheusClient**: Handles connection setup, timeouts, query execution (`/api/v1/query`), and range query execution (`/api/v1/query_range`).
- **Collector**: Automatically discovers pods, retrieves CPU utilization, memory working set size, and container restart counts for any targeted namespace, organizing them by pod name.

### 2. Feature Service (`feature-service`)
Processes time-series range metrics from Prometheus and transforms them into input features for downstream Machine Learning models.
- **Range Queries**: Extracts historical metrics over configurable windows and steps.
- **Statistical Features**: Calculates current, average, min, and max resource usages.
- **Trend Calculation**: Fits an analytical linear regression slope over historical metrics to determine the rate of change per second (`cores/sec` for CPU and `bytes/sec` for Memory).

### 3. Prediction Service (`prediction-service`)
Combines collector data, ML scoring, and rule interpretations to expose REST endpoints and feed real-time monitoring targets.
- **PredictionOrchestrator**: Coordinates features loading, anomaly validation, risk calculation, and mapping scaling recommendations.
- **AnomalyDetector**: Wraps the unsupervised Isolation Forest model to detect statistical CPU/memory usage outliers.
- **RuleEngine**: Interprets model outputs and operational rules (e.g. restart counts and leak trend slopes) to grade pod health levels.
- **MonitoringWorker**: Runs a continuous scanning daemon that gathers namespaces metrics in the background and populates Prometheus Gauge targets.
- **MetricsExporter**: Exposes metrics endpoint (`/metrics`) mapped to Prometheus and handles dynamic stale metrics purging.

