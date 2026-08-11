# Controlled Workload Generation

This directory contains manifests to generate predictable workloads inside the `kubeguard-test` namespace for validation of KubeGuard AI monitoring.

## Manifests

1. **`test-namespace.yaml`**: Creates the isolated `kubeguard-test` namespace.
2. **`cpu-stress.yaml`**: A deployment containing an inline Python loop to burn CPU.
3. **`memory-growth.yaml`**: A deployment allocating memory in chunks over time.

---

## Usage

### 1. Start Workloads
Deploy all manifests to create the namespace and start generating workload:
```bash
kubectl apply -f kubernetes/manifests/
```

### 2. Verify with Prometheus
Run standard PromQL queries using curl or Grafana to watch metrics:

- **CPU**:
  ```promql
  sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="kubeguard-test", container!="", container!="POD"}[5m]))
  ```
- **Memory**:
  ```promql
  sum by (pod) (container_memory_working_set_bytes{namespace="kubeguard-test", container!="", container!="POD"})
  ```

### 3. Run the Feature Pipeline
Extract historical data and calculate features for the stress-test namespace:
```bash
python feature-service/src/feature_service.py --namespace kubeguard-test
```

### 4. Cleanup
Remove the test namespace and all deployed workloads:
```bash
kubectl delete namespace kubeguard-test
```
