# KubeGuard CLI

Command-line interface for installing, inspecting, and operating KubeGuard AI.

---

## Requirements

| Tool | Minimum | Purpose |
|------|---------|---------|
| Python | 3.9+ | Runtime |
| kubectl | Any | Kubernetes cluster access |
| Helm | v3+ | Chart installation |
| KubeGuard repo | — | Helm chart at `helm/kubeguard/` |
| kube-prometheus-stack | — | Prometheus + Alertmanager backing |

---

## Installation

From the KubeGuard repository root:

```bash
cd cli
pip install .
```

Verify:

```bash
kubeguard --help
```

Development install (with test dependencies):

```bash
pip install -e ".[dev]"
```

---

## Commands

| Command | Description |
|---------|-------------|
| `kubeguard version` | Show CLI and app version |
| `kubeguard install` | Install KubeGuard into a Kubernetes cluster |
| `kubeguard status` | Show current installation and runtime status |
| `kubeguard pods` | Display pod risk scores |
| `kubeguard alerts` | Display active KubeGuard alerts |
| `kubeguard uninstall` | Remove the KubeGuard Helm release |

---

## Global Options

These options apply to every command:

| Option | Default | Description |
|--------|---------|-------------|
| `--context TEXT` | current-context | Kubernetes context |
| `--namespace TEXT` | `kubeguard` | KubeGuard namespace |

Example:

```bash
kubeguard --context kind-kubeguard status
```

---

## Examples

### Install KubeGuard

```bash
# Default install
kubeguard install

# Custom monitoring interval and namespaces
kubeguard install --interval 60 --namespaces demo,kubeguard-test

# Specify a non-default namespace
kubeguard install --namespace my-kubeguard

# Point to chart explicitly
kubeguard install --chart-path /path/to/helm/kubeguard
```

### Check Status

```bash
kubeguard status

# JSON output
kubeguard status --json
```

### View Pod Risk Scores

```bash
# All pods
kubeguard pods

# Filter by namespace
kubeguard pods --namespace demo

# Filter by risk level
kubeguard pods --risk high

# Combined
kubeguard pods --namespace kubeguard-test --risk high

# JSON output
kubeguard pods --json
```

### View Active Alerts

```bash
kubeguard alerts

# JSON output
kubeguard alerts --json

# Custom Alertmanager service name
kubeguard alerts --alertmanager-svc my-alertmanager --alertmanager-ns monitoring
```

### Uninstall

```bash
# Interactive confirmation
kubeguard uninstall

# Skip confirmation
kubeguard uninstall --yes
```

---

## Multi-Context Usage

```bash
# Use a specific context for every command
kubeguard --context kind-kubeguard-fresh status
kubeguard --context kind-kubeguard pods
kubeguard --context kind-kubeguard alerts
```

The `--context` flag only affects the duration of the command. Your default
context is never permanently changed.

---

## Configuration Options (install)

| Option | Helm Value | Default |
|--------|-----------|---------|
| `--interval N` | `monitoring.intervalSeconds` | `30` |
| `--namespaces TEXT` | `monitoring.namespaces` | `demo,kubeguard-test` |

---

## API Access

The CLI does **not** require a public endpoint. All API access uses transient
`kubectl port-forward` tunnels:

- `kubeguard status` → `svc/kubeguard:8000` (`/health`)
- `kubeguard pods` → `svc/kubeguard:8000` (`/metrics`)
- `kubeguard alerts` → `svc/kube-prometheus-stack-alertmanager:9093` (`/api/v2/alerts`)

Tunnels are opened for the duration of the command and then closed.

---

## Troubleshooting

### `kubectl` or `helm` not found

```
Error: kubectl is not installed or not on PATH.
```

Install kubectl: https://kubernetes.io/docs/tasks/tools/  
Install Helm: https://helm.sh/docs/intro/install/

### Cluster unreachable

```
Error: Kubernetes cluster is unreachable.
```

Check: `kubectl cluster-info --context <your-context>`

### KubeGuard not installed

```
KubeGuard is not installed in namespace 'kubeguard'.
Run kubeguard install to install.
```

### Port-forward timeout

The pod may still be initializing. Wait 30 seconds and retry. Check:

```bash
kubectl get pods -n kubeguard
kubectl logs -n kubeguard deployment/kubeguard --tail=20
```

### Alertmanager not found

If using a custom Prometheus stack name:

```bash
kubeguard alerts \
  --alertmanager-svc my-alertmanager-svc \
  --alertmanager-ns monitoring
```

---

## Running Tests

```bash
cd cli
pip install -e ".[dev]"
pytest kubeguard_cli/tests/ -v
```

All tests mock subprocess calls — no Kubernetes cluster is required.
