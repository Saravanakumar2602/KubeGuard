# KubeGuard Helm Chart

This Helm chart packages KubeGuard AI prediction pipeline services, Observability service monitors, Prometheus alerting rules, and Grafana dashboard configurations.

## Requirements
- Kubernetes cluster
- Helm v3
- Prometheus Operator (e.g. `kube-prometheus-stack` Helm installation)
- Grafana (supporting dashboard sidecar discovery)

---

## Installation

To install KubeGuard using this chart into the `kubeguard` namespace:

```bash
helm install kubeguard helm/kubeguard \
  --namespace kubeguard \
  --create-namespace
```

---

## Configuration Options (`values.yaml`)

The following table lists the configurable parameters of the KubeGuard chart and their default values:

| Parameter | Description | Default |
|---|---|---|
| `namespace` | Kubernetes namespace for chart deployment | `kubeguard` |
| `createNamespace` | Create the namespace during helm templates | `false` |
| `replicaCount` | Number of replicas for prediction service | `1` |
| `image.repository` | Docker image repository | `kubeguard-prediction-service` |
| `image.tag` | Docker image tag | `0.1.2` |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `service.type` | Kubernetes service type | `ClusterIP` |
| `service.port` | Service listening port | `8000` |
| `resources.requests.cpu` | CPU resource requests | `100m` |
| `resources.requests.memory` | Memory resource requests | `128Mi` |
| `resources.limits.cpu` | CPU resource limits | `500m` |
| `resources.limits.memory` | Memory resource limits | `256Mi` |
| `monitoring.intervalSeconds` | Monitoring scanning worker period in seconds | `30` |
| `monitoring.namespaces` | Monitored Kubernetes namespaces comma-separated | `"demo,kubeguard-test"` |
| `prometheus.url` | Internal endpoint URL of cluster Prometheus service | `"http://kube-prometheus-stack-prometheus.monitoring.svc:9090"` |
| `serviceMonitor.enabled` | Enable ServiceMonitor generation for scrape discovery | `true` |
| `serviceMonitor.interval` | Scrape period for metrics scraping | `15s` |
| `prometheusRule.enabled` | Enable PrometheusRule alerting generation | `true` |
| `grafanaDashboard.enabled` | Enable Grafana dashboard ConfigMap provisioning | `true` |

---

## Examples: Overriding Configuration

### 1. Override Scrape Settings and Target Namespaces
To scan only the `demo` namespace every `60 seconds` with resource allocation updates:

```bash
helm install kubeguard helm/kubeguard \
  --namespace kubeguard \
  --create-namespace \
  --set monitoring.intervalSeconds=60 \
  --set monitoring.namespaces="demo" \
  --set resources.limits.cpu=1000m
```

### 2. Disable PrometheusRules or ServiceMonitors
If the target cluster doesn't run Prometheus Operator:

```bash
helm install kubeguard helm/kubeguard \
  --namespace kubeguard \
  --create-namespace \
  --set serviceMonitor.enabled=false \
  --set prometheusRule.enabled=false
```

---

## Upgrade Configurations
To update release parameters:

```bash
helm upgrade kubeguard helm/kubeguard \
  --namespace kubeguard \
  --set monitoring.intervalSeconds=45
```

---

## Uninstalling
To completely remove the KubeGuard release:

```bash
helm uninstall kubeguard --namespace kubeguard
```

---

## Local Development in Kind
1. Rebuild and load docker image in local Kind nodes:
   ```bash
   docker build -f prediction-service/Dockerfile -t kubeguard-prediction-service:0.1.2 .
   kind load docker-image kubeguard-prediction-service:0.1.2 --name kubeguard
   ```
2. Install via Helm using target tag:
   ```bash
   helm install kubeguard helm/kubeguard \
     --namespace kubeguard \
     --create-namespace \
     --set image.tag="0.1.2"
   ```
