# KubeGuard AI — Contributor Guide

Welcome! Thank you for contributing to **KubeGuard AI**. This guide outlines development setup, testing standards, Helm chart validation, and contribution workflows.

---

## 1. Repository Overview

KubeGuard AI is organized into modular services:

- **`prediction-service/`**: Core FastAPI REST server, Isolation Forest ML model store, SQLite feature store, Rule Engine, and monitoring worker loop.
- **`collector-service/`**: Prometheus metrics scraping client and pod metric parser.
- **`feature-service/`**: Pod feature calculation and linear regression trend computation.
- **`cli/`**: Python Typer/Rich command-line interface (`kubeguard`).
- **`helm/kubeguard/`**: Versioned Helm chart for Kubernetes deployment.
- **`kubernetes/`**: PrometheusRule manifests, Grafana dashboards, and test stress workloads.

---

## 2. Local Environment Setup

### Prerequisites
- Python 3.11+
- Helm v3+
- Docker & Kind (for local cluster testing)

### Virtual Environment
```bash
python -m venv venv
# On Linux/macOS:
source venv/bin/activate
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1

pip install -r prediction-service/requirements.txt
cd cli && pip install -e . && cd ..
```

---

## 3. Running Unit Tests

Execute prediction service tests:
```bash
pytest prediction-service/tests/ -v
```

Execute CLI tests:
```bash
pytest cli/kubeguard_cli/tests/ -v
```

Alternatively, use the Makefile shortcuts:
```bash
make test
make cli-test
```

---

## 4. Helm Chart Validation

Before submitting changes to `helm/kubeguard/`:

```bash
# 1. Lint chart
helm lint helm/kubeguard

# 2. Dry-run template rendering
helm template kubeguard helm/kubeguard --namespace kubeguard

# 3. Test persistence overrides
helm template kubeguard helm/kubeguard --namespace kubeguard --set persistence.storageClassName=gp3
```

---

## 5. Development Workflow & Rules

1. **Backwards Compatibility**: Do not remove existing endpoints (`/health`, `/ready`, `/metrics`, `/predict`, `/incidents`) or CLI commands (`pods`, `status`, `incidents`, `alerts`).
2. **Deterministic Rules & Scoring**: Do not alter risk weight scoring boundaries without explicit alignment.
3. **SQLite Concurrency**: Ensure all database connections configure `PRAGMA journal_mode=WAL;`, `busy_timeout=5000;`, and `foreign_keys=ON;`.
4. **Atomic File Storage**: Use `.tmp` writing + `os.replace()` for file persistence to prevent corrupted artifacts.
