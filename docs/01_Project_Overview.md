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
