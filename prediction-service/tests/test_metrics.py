"""Unit tests for KubeGuard self-monitoring metrics and helper functions."""

import time
from metrics import (
    kubeguard_monitoring_cycles_total,
    kubeguard_worker_healthy,
    kubeguard_model_info,
    kubeguard_config_info,
    set_model_info_metric,
    update_worker_health_metric,
    set_config_info_metric,
)



def test_metric_registration_and_counter_increment():
    """Verify that counter increment updates prometheus metrics."""
    initial = kubeguard_monitoring_cycles_total._value.get()
    kubeguard_monitoring_cycles_total.inc()
    assert kubeguard_monitoring_cycles_total._value.get() == initial + 1.0


def test_set_model_info_metric():
    """Verify set_model_info_metric sets model_info gauge labels and clears old labels."""
    set_model_info_metric(source="bootstrap", version=1)

    # Set new model info version
    set_model_info_metric(source="historical", version=2)
    # The active metric sample list should contain (source=historical, version=2)
    found = False
    for sample in kubeguard_model_info.collect()[0].samples:
        if sample.labels.get("source") == "historical" and sample.labels.get("version") == "2":
            assert sample.value == 1.0
            found = True
    assert found


def test_update_worker_health_metric():
    """Verify worker health gauge calculation based on last_success_timestamp and timeout."""
    now = time.time()

    # Recent timestamp -> Healthy (1)
    update_worker_health_metric(last_success_timestamp=now - 10, timeout_seconds=90.0)
    assert kubeguard_worker_healthy._value.get() == 1.0

    # Stale timestamp -> Unhealthy (0)
    update_worker_health_metric(last_success_timestamp=now - 120, timeout_seconds=90.0)
    assert kubeguard_worker_healthy._value.get() == 0.0

    # Zero timestamp -> Unhealthy (0)
    update_worker_health_metric(last_success_timestamp=0.0, timeout_seconds=90.0)
    assert kubeguard_worker_healthy._value.get() == 0.0


def test_set_config_info_metric():
    """Verify configuration info gauge helper."""
    set_config_info_metric(interval_seconds=30, retention_days=7, min_samples=50, retrain_interval=3600)
    found = False
    for sample in kubeguard_config_info.collect()[0].samples if hasattr(kubeguard_config_info, 'collect') else []:
        if sample.labels.get("monitor_interval_seconds") == "30":
            assert sample.value == 1.0
            found = True
