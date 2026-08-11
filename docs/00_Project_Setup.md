# Project Setup

This document describes how to set up the KubeGuard AI local development environment.

## Prerequisites

- **Docker Desktop**: Installed and running on Windows.
- **Kind**: For running local Kubernetes clusters.
- **Helm**: Kubernetes package manager.
- **Python 3.11+**: Installed locally.

---

## Local Cluster Setup

1. **Create Kind Cluster**:
   Create a local cluster named `kubeguard` using Kind:
   ```bash
   kind create cluster --name kubeguard
   ```

2. **Install Prometheus & Grafana (kube-prometheus-stack)**:
   Add the Helm repository and install the stack:
   ```bash
   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
   helm repo update
   helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
   ```

3. **Deploy the Test Application**:
   Create the `demo` namespace and deploy the target test application (`demo-nginx` with 2 replicas):
   ```bash
   kubectl create namespace demo
   kubectl create deployment demo-nginx --image=nginx:alpine --replicas=2 -n demo
   ```

---

## Exposing Prometheus Locally

For the Python services to communicate with Prometheus during local development, expose the Prometheus service using `port-forward`:

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
```

Prometheus will then be accessible at:
```text
http://localhost:9090
```
