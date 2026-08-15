# Deployment Guide

This document guides you through deploying KubeGuard AI inside a local Kind Kubernetes cluster using the reusable Helm chart.

---

## 1. Prerequisites

Before installing the chart, ensure you have:
1. A local Kind cluster running:
   ```bash
   kind get clusters
   ```
2. Helm v3 installed:
   ```bash
   helm version
   ```
3. Prometheus Operator installed (e.g. via `kube-prometheus-stack` Helm chart).
4. KubeGuard Docker image built and loaded onto your Kind node:
   ```bash
   docker build -f prediction-service/Dockerfile -t kubeguard-prediction-service:0.1.6 .
   kind load docker-image kubeguard-prediction-service:0.1.6 --name kubeguard
   ```

---

## 2. Deploying via Helm

Deploy KubeGuard into the `kubeguard` namespace:

```bash
helm install kubeguard helm/kubeguard \
  --namespace kubeguard \
  --create-namespace
```

### Verifying Release Resources
Ensure the pods, service, and custom resources are active:

```bash
kubectl get pods -n kubeguard
kubectl get servicemonitor -n kubeguard
kubectl get prometheusrule -n kubeguard
```

---

## 3. Upgrading Configurations

To dynamically update configuration settings (e.g. changing namespaces to scan or the scanning frequency):

```bash
helm upgrade kubeguard helm/kubeguard \
  --namespace kubeguard \
  --set monitoring.intervalSeconds=45 \
  --set monitoring.namespaces="demo,kubeguard-test"
```

---

## 4. Uninstalling

To uninstall and clean up all release resources:

```bash
helm uninstall kubeguard --namespace kubeguard
```
*Note: This deletes all KubeGuard deployments, rules, dashboards, and configurations, but preserves target demo/monitoring test workloads.*
