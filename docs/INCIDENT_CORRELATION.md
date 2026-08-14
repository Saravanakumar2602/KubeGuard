# KubeGuard AI — Event Correlation & Incident Context Architecture

This document details the event correlation, incident lifecycle, signal tracking, Alertmanager integration, and operator visibility introduced in Step 18 of KubeGuard AI.

---

## 1. Incident Correlation Architecture Overview

KubeGuard correlates isolated workload telemetry signals (CPU/Memory trends, restart counts, Isolation Forest ML anomalies) and Prometheus Alertmanager alerts into unified, persistent incident contexts.

```
Workload Signals (CPU, Mem, Restarts, ML Anomaly) + Alertmanager Firing Alerts
                                      │
                                      ▼
                        PredictionOrchestrator / worker.py
                                      │
                                      ▼
                       IncidentManager.process_assessment()
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
   New Incident (First Risk)                        Existing Active Incident
  - Generate Incident ID                           - Check Signal Transitions
  - Record Initial Signals                         - Emits Timeline Events on Change
  - Create Timeline Events                         - Update Score & Recommendation
              │                                               │
              └───────────────────────┬───────────────────────┘
                                      ▼
                       SQLite IncidentStore (/data/kubeguard.db)
                                      │
                                      ├── Resolution Grace Period Check
                                      │   (Clear signals > 120s ──► Resolve Incident)
                                      │
                                      ▼
                       Prometheus Metrics / API / CLI
                       - GET /incidents & GET /incidents/{id}
                       - `kubeguard incidents` CLI command
                       - kubeguard_active_incidents gauge
```

---

## 2. Incident Domain Model & Lifecycle

### Status States
- **`active`**: Monitored workload has active risk signals or is within the resolution grace period window.
- **`resolved`**: Workload risk signals have returned to normal baseline and the grace period has elapsed.

### Deduplication Policy
- An active incident is uniquely identified by `(namespace, pod)`.
- Multiple monitoring scan cycles update the **same** active incident rather than spawning duplicate incidents.
- If a new risk condition arises *after* a previous incident was resolved, a new incident instance is created, preserving historical incident records.

---

## 3. SQLite Persistence Schema

All incident data is stored in the embedded SQLite database (`/data/kubeguard.db`) alongside feature observations.

### Table: `incidents`
```sql
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT UNIQUE NOT NULL,
    namespace TEXT NOT NULL,
    pod TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    status TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    recommendation TEXT NOT NULL
);
```

### Table: `incident_signals`
```sql
CREATE TABLE IF NOT EXISTS incident_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    signal_name TEXT NOT NULL,
    severity TEXT NOT NULL,
    value TEXT,
    description TEXT,
    detected_at TEXT NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES incidents(incident_id) ON DELETE CASCADE
);
```

### Table: `incident_events`
```sql
CREATE TABLE IF NOT EXISTS incident_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES incidents(incident_id) ON DELETE CASCADE
);
```

### Table: `incident_alerts`
```sql
CREATE TABLE IF NOT EXISTS incident_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    alert_name TEXT NOT NULL,
    severity TEXT NOT NULL,
    fired_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY(incident_id) REFERENCES incidents(incident_id) ON DELETE CASCADE
);
```

---

## 4. Signal Change Detection & Timeline Events

Timeline events are generated strictly on meaningful state transitions (avoiding noise on static monitoring cycles):

- `incident_created`: Emitted when pod enters a initial risk state.
- `risk_detected`: Emitted on initial risk assessment.
- `risk_escalated` / `risk_deescalated`: Emitted when risk level changes (e.g. LOW → HIGH or HIGH → LOW).
- `ml_anomaly_detected`: Emitted when Isolation Forest flags an anomaly.
- `memory_growth_detected`: Emitted when memory trend exceeds threshold (1000 B/s).
- `cpu_trend_detected`: Emitted when CPU trend exceeds threshold (0.0001 cores/s).
- `restart_count_elevated`: Emitted when pod restart count increases.
- `alert_fired` / `alert_resolved`: Emitted when correlated Prometheus alerts transition state.
- `incident_resolved`: Emitted when signals remain clear past the resolution grace period.

---

## 5. Alertmanager Correlation & Resilience

- **Alertmanager Endpoint**: Configured via `ALERTMANAGER_URL` (default: `http://kube-prometheus-stack-alertmanager.monitoring.svc:9093`).
- **Scrape Frequency**: Queried once per 30-second monitoring cycle.
- **Matching Criteria**: Alert labels matching `exported_namespace==ns` & `exported_pod==pod` (or `namespace` & `pod`).
- **Failure Resilience**: If Alertmanager is unreachable, KubeGuard logs a warning, skips alert correlation, and continues risk evaluation and monitoring cycle execution without interruption.

---

## 6. Resolution Grace Period & Retention

- **`INCIDENT_RESOLUTION_GRACE_SECONDS`** (default: `120` seconds): Prevents incident flapping caused by transient scrape drops.
- **`INCIDENT_RETENTION_DAYS`** (default: `30` days): Automatically purges resolved incidents older than 30 days. Active incidents are never purged.

---

## 7. HTTP API & CLI Reference

### API Endpoints
- `GET /incidents?namespace=demo&status=active&limit=50`: Query active or resolved incidents.
- `GET /incidents/{incident_id}`: Retrieve full incident context including signals, timeline events, correlated alerts, and recommendations. Returns HTTP 404 if not found.

### CLI Commands
```bash
# List all incidents
kubeguard incidents

# Filter active incidents in a namespace
kubeguard incidents --status active --namespace demo

# Inspect detailed incident timeline and context
kubeguard incidents --id demo/demo-nginx-6b89dd5974-6v2g5/1786689503
```

---

## 8. Prometheus Metrics Taxonomy

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `kubeguard_incidents_created_total` | Counter | None | Total incidents created |
| `kubeguard_incidents_resolved_total` | Counter | None | Total incidents resolved |
| `kubeguard_active_incidents` | Gauge | `risk_level` | Current active incidents count by risk level |
| `kubeguard_incident_duration_seconds` | Histogram | None | Resolved incident duration in seconds |
