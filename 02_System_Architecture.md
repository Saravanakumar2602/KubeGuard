# 🛡️ What Are We Building?

KubeGuard AI is an **installable Kubernetes plugin** that brings AI-powered health monitoring and predictive recommendations to any Kubernetes cluster.

Instead of creating another monitoring dashboard, we are building a **cloud-native extension** that integrates with the tools DevOps engineers already use, such as Prometheus and Grafana.

The goal is simple:

> **Install once, monitor every pod, predict failures, and provide intelligent recommendations.**

Users will install KubeGuard AI using a single Helm command:

```bash
helm repo add kubeguard https://github.com/kubeguard-ai/charts

helm install kubeguard kubeguard/kubeguard-ai
```

After installation, KubeGuard AI automatically:

- Connects to Prometheus
- Collects Kubernetes metrics
- Builds ML features
- Detects anomalies
- Predicts unhealthy pods
- Generates scaling recommendations
- Creates Grafana dashboards
- Exposes REST APIs
- Sends alerts (Slack/Email in future versions)

Everything runs **inside the user's Kubernetes cluster**, making the installation simple and secure.

---

# 🤔 Why Build It as a Kubernetes Plugin?

There are several ways this project could have been built.

## Option 1 — Standalone Web Dashboard ❌

A separate website that displays Kubernetes metrics.

Problems:

- Users need to open another application.
- Existing monitoring tools already provide dashboards.
- Doesn't integrate naturally into Kubernetes workflows.

---

## Option 2 — SaaS Platform ❌

A cloud-hosted platform similar to Datadog or New Relic.

Problems:

- Requires cloud infrastructure.
- User authentication.
- Data privacy concerns.
- Higher operational costs.
- Too complex for the first version.

---

## ✅ Option 3 — Kubernetes Plugin (Chosen Approach)

This is the approach used by many successful cloud-native projects.

KubeGuard AI is deployed directly inside a Kubernetes cluster as its own set of services.

```
                    Kubernetes Cluster

        ┌─────────────────────────────────────┐

        │  Prometheus                         │
        │  Grafana                            │
        │  KubeGuard AI                       │
        │     ├── Collector Service           │
        │     ├── Feature Service             │
        │     ├── ML Engine                   │
        │     ├── Recommendation Engine       │
        │     └── FastAPI                     │

        └─────────────────────────────────────┘
```

This approach offers several advantages:

- Native Kubernetes deployment
- Easy installation using Helm
- No separate infrastructure required
- Works with existing Prometheus and Grafana installations
- Easy to upgrade
- Easy to uninstall
- Cloud-native architecture
- Familiar workflow for DevOps engineers

---

# 🎯 Our Vision

KubeGuard AI is **not intended to replace Prometheus or Grafana.**

Instead, it acts as an **AI layer** on top of the existing Kubernetes observability stack.

```
Applications

        │

        ▼

Kubernetes

        │

        ▼

Prometheus
(Collects Metrics)

        │

        ▼

KubeGuard AI
(Analyzes + Predicts)

        │

        ▼

Grafana
(Displays Insights)
```

Prometheus answers:

> "What is happening?"

KubeGuard AI answers:

> "What is likely to happen next, and what should you do about it?"

This makes Kubernetes monitoring proactive instead of reactive.
