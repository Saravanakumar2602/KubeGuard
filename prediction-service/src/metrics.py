from prometheus_client import Gauge

# 1. Risk score
kubeguard_pod_risk_score = Gauge(
    "kubeguard_pod_risk_score",
    "Operational risk score of the pod (0-100)",
    ["namespace", "pod"]
)

# 2. Anomaly status
kubeguard_pod_anomaly = Gauge(
    "kubeguard_pod_anomaly",
    "Anomaly detection status (0 = normal, 1 = anomalous)",
    ["namespace", "pod"]
)

# 3. Risk level (one-hot)
kubeguard_pod_risk_level = Gauge(
    "kubeguard_pod_risk_level",
    "One-hot encoded risk level of the pod",
    ["namespace", "pod", "level"]
)

# 4. CPU trend
kubeguard_pod_cpu_trend = Gauge(
    "kubeguard_pod_cpu_trend",
    "CPU usage trend in cores per second",
    ["namespace", "pod"]
)

# 5. Memory trend
kubeguard_pod_memory_trend_bytes_per_second = Gauge(
    "kubeguard_pod_memory_trend_bytes_per_second",
    "Memory usage trend in bytes per second",
    ["namespace", "pod"]
)

# 6. Restart count
kubeguard_pod_restart_count = Gauge(
    "kubeguard_pod_restart_count",
    "Number of restarts of the pod",
    ["namespace", "pod"]
)


def update_pod_metrics(features, anomaly, risk) -> None:
    """Update all Prometheus metrics for a pod based on prediction pipeline results.

    Args:
        features: PodFeatures calculated metrics.
        anomaly: AnomalyResult from Isolation Forest model.
        risk: RiskResult from Rule Engine.
    """
    ns = features.namespace
    pod = features.pod

    # 1. Risk score
    kubeguard_pod_risk_score.labels(namespace=ns, pod=pod).set(risk.risk_score)

    # 2. Anomaly status
    kubeguard_pod_anomaly.labels(namespace=ns, pod=pod).set(1 if anomaly.is_anomaly else 0)

    # 3. Risk level (one-hot)
    kubeguard_pod_risk_level.labels(namespace=ns, pod=pod, level="LOW").set(1 if risk.risk_level == "LOW" else 0)
    kubeguard_pod_risk_level.labels(namespace=ns, pod=pod, level="MEDIUM").set(1 if risk.risk_level == "MEDIUM" else 0)
    kubeguard_pod_risk_level.labels(namespace=ns, pod=pod, level="HIGH").set(1 if risk.risk_level == "HIGH" else 0)

    # 4. CPU trend
    if features.cpu_trend is not None:
        kubeguard_pod_cpu_trend.labels(namespace=ns, pod=pod).set(features.cpu_trend)

    # 5. Memory trend
    if features.memory_trend is not None:
        kubeguard_pod_memory_trend_bytes_per_second.labels(namespace=ns, pod=pod).set(features.memory_trend)

    # 6. Restart count
    if features.restart_count is not None:
        kubeguard_pod_restart_count.labels(namespace=ns, pod=pod).set(features.restart_count)
