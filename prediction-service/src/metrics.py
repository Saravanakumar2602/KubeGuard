import time
from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Workload Telemetry Metrics (Step 10-16)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Platform Self-Observability Metrics (Step 17)
# ---------------------------------------------------------------------------

# Monitoring Worker Metrics
kubeguard_monitoring_cycles_total = Counter(
    "kubeguard_monitoring_cycles_total",
    "Total monitoring cycles executed"
)
kubeguard_monitoring_cycle_failures_total = Counter(
    "kubeguard_monitoring_cycle_failures_total",
    "Total monitoring cycle failures"
)
kubeguard_monitoring_cycle_duration_seconds = Histogram(
    "kubeguard_monitoring_cycle_duration_seconds",
    "Monitoring cycle execution duration in seconds"
)

# Prediction Metrics
kubeguard_pod_predictions_total = Counter(
    "kubeguard_pod_predictions_total",
    "Total pod predictions evaluated",
    ["namespace", "result"]
)
kubeguard_prediction_duration_seconds = Histogram(
    "kubeguard_prediction_duration_seconds",
    "Prediction execution duration in seconds",
    ["namespace"]
)

# Feature Store Metrics
kubeguard_feature_store_observations_total = Counter(
    "kubeguard_feature_store_observations_total",
    "Feature observations successfully stored"
)
kubeguard_feature_store_errors_total = Counter(
    "kubeguard_feature_store_errors_total",
    "Feature store operation failures"
)
kubeguard_feature_store_records = Gauge(
    "kubeguard_feature_store_records",
    "Current number of stored feature observations"
)

# Model Lifecycle Metrics
kubeguard_model_training_total = Counter(
    "kubeguard_model_training_total",
    "Model training executions",
    ["source"]
)
kubeguard_model_training_duration_seconds = Histogram(
    "kubeguard_model_training_duration_seconds",
    "Model training duration in seconds",
    ["source"]
)
kubeguard_model_load_total = Counter(
    "kubeguard_model_load_total",
    "Model load attempts",
    ["result"]
)
kubeguard_model_info = Gauge(
    "kubeguard_model_info",
    "Active Isolation Forest model state and provenance",
    ["source", "version"]
)

# Worker Health & Timestamps
kubeguard_worker_last_success_timestamp = Gauge(
    "kubeguard_worker_last_success_timestamp",
    "Unix timestamp of the last successful monitoring cycle"
)
kubeguard_worker_last_cycle_timestamp = Gauge(
    "kubeguard_worker_last_cycle_timestamp",
    "Unix timestamp of the most recent monitoring cycle"
)
kubeguard_worker_pods_evaluated = Gauge(
    "kubeguard_worker_pods_evaluated",
    "Number of pods evaluated in the most recent monitoring cycle"
)
kubeguard_worker_healthy = Gauge(
    "kubeguard_worker_healthy",
    "Monitoring worker health state (1 = healthy, 0 = unhealthy)"
)

# Configuration Info
kubeguard_config_info = Gauge(
    "kubeguard_config_info",
    "Active KubeGuard configuration info",
    ["monitor_interval_seconds", "retention_days", "min_training_samples", "retrain_interval_seconds"]
)


def set_model_info_metric(source: str, version: int) -> None:
    """Clear stale model_info metrics and record active model state."""
    try:
        kubeguard_model_info.clear()
    except Exception:
        pass
    kubeguard_model_info.labels(source=source, version=str(version)).set(1)


def update_worker_health_metric(last_success_timestamp: float, timeout_seconds: float = 90.0) -> None:
    """Update worker health gauge based on last successful monitoring cycle time."""
    if last_success_timestamp > 0 and (time.time() - last_success_timestamp) <= timeout_seconds:
        kubeguard_worker_healthy.set(1)
    else:
        kubeguard_worker_healthy.set(0)


def set_config_info_metric(
    interval_seconds: float, retention_days: int, min_samples: int, retrain_interval: float
) -> None:
    """Publish configuration gauge labels."""
    try:
        kubeguard_config_info.clear()
    except Exception:
        pass
    kubeguard_config_info.labels(
        monitor_interval_seconds=str(interval_seconds),
        retention_days=str(retention_days),
        min_training_samples=str(min_samples),
        retrain_interval_seconds=str(retrain_interval),
    ).set(1)



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


def cleanup_stale_metrics(active_pods: list) -> None:
    """Purge metrics for pods that are no longer active in the cluster.

    Args:
        active_pods: A list of tuples containing (pod_name, namespace) for active pods.
    """
    # Create set of active (namespace, pod) tuples for O(1) lookup
    active_set = {(ns, pod) for pod, ns in active_pods}

    # Extract currently registered labels keys
    current_keys = list(kubeguard_pod_risk_score._metrics.keys())

    for ns, pod in current_keys:
        if (ns, pod) not in active_set:
            # Stale pod -> remove metrics time-series
            try:
                kubeguard_pod_risk_score.remove(ns, pod)
            except KeyError:
                pass
            try:
                kubeguard_pod_anomaly.remove(ns, pod)
            except KeyError:
                pass
            try:
                kubeguard_pod_cpu_trend.remove(ns, pod)
            except KeyError:
                pass
            try:
                kubeguard_pod_memory_trend_bytes_per_second.remove(ns, pod)
            except KeyError:
                pass
            try:
                kubeguard_pod_restart_count.remove(ns, pod)
            except KeyError:
                pass

            # Risk levels (one-hot keys)
            for lvl in ["LOW", "MEDIUM", "HIGH"]:
                try:
                    kubeguard_pod_risk_level.remove(ns, pod, lvl)
                except KeyError:
                    pass

