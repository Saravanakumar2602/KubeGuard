import os
import sys
import time
import logging
import threading
from typing import List, Tuple

logger = logging.getLogger("kubeguard-worker")

# Resolve paths
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from config import KubeGuardConfig
from metrics import (
    cleanup_stale_metrics,
    kubeguard_monitoring_cycles_total,
    kubeguard_monitoring_cycle_failures_total,
    kubeguard_monitoring_cycle_duration_seconds,
    kubeguard_pod_predictions_total,
    kubeguard_worker_last_success_timestamp,
    kubeguard_worker_last_cycle_timestamp,
    kubeguard_worker_pods_evaluated,
    update_worker_health_metric,
    set_config_info_metric,
)


class MonitoringWorker:
    """Background monitoring worker that discovers pods, evaluates predictions, and updates metrics."""

    def __init__(self, orchestrator, config: KubeGuardConfig | None = None) -> None:
        self.orchestrator = orchestrator
        self.config = config or KubeGuardConfig.from_env()

        self.interval = self.config.monitor_interval_seconds
        self.namespaces = self.config.monitor_namespaces
        self.retention_days = self.config.feature_retention_days
        self.health_timeout = self.config.worker_health_timeout_seconds

        self.last_success_timestamp: float = 0.0
        self._stop_event = threading.Event()
        self._thread = None

        set_config_info_metric(
            interval_seconds=self.interval,
            retention_days=self.retention_days,
            min_samples=self.config.min_training_samples,
            retrain_interval=self.config.model_retrain_interval_seconds,
        )

    def start(self) -> None:
        """Start the background periodic monitoring thread."""
        if self._thread is not None:
            logger.warning("Monitoring worker is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="KubeGuardMonitoringWorker"
        )
        self._thread.start()
        logger.info(f"Monitoring worker started. Interval: {self.interval}s, Namespaces: {self.namespaces}")

    def stop(self) -> None:
        """Stop the background periodic monitoring thread."""
        if self._thread is None:
            return

        logger.info("Stopping monitoring worker...")
        self._stop_event.set()
        self._thread.join(timeout=5)
        self._thread = None
        logger.info("Monitoring worker stopped successfully.")

    def _run_loop(self) -> None:
        # Wait a short delay on startup for Prometheus to stabilize
        time.sleep(5)
        last_retrain_check = time.time()
        last_retention_check = 0.0

        while not self._stop_event.is_set():
            cycle_start = time.time()
            kubeguard_monitoring_cycles_total.inc()
            kubeguard_worker_last_cycle_timestamp.set(cycle_start)

            logger.info("Starting periodic namespace metrics scan...")
            active_pods = []
            cycle_failed = False

            try:
                # 1. Ensure the detector is trained
                if not self.orchestrator.detector.is_fitted:
                    logger.info("Model not yet trained. Triggering baseline model initialization...")
                    try:
                        self.orchestrator.initialize_model()
                    except Exception as init_err:
                        logger.error(f"Error training model during scan startup: {init_err}")

                if self.orchestrator.detector.is_fitted:
                    # 2. Discover pods in all configured namespaces
                    for ns in self.namespaces:
                        if self._stop_event.is_set():
                            break
                        logger.info(f"Scanning namespace '{ns}' for pods...")
                        try:
                            discovered = self.orchestrator.collector._discover_pods(ns)
                            active_pods.extend(discovered)
                        except Exception as disc_err:
                            logger.error(f"Prometheus error discovering pods in namespace '{ns}': {disc_err}")

                    # 3. Evaluate each discovered pod with failure isolation
                    successful_evals = 0
                    for pod_name, ns in active_pods:
                        if self._stop_event.is_set():
                            break
                        logger.info(f"Evaluating pod '{pod_name}' in namespace '{ns}'...")
                        try:
                            self.orchestrator.predict(namespace=ns, pod=pod_name)
                            successful_evals += 1
                            logger.info(f"Metrics updated successfully for pod '{pod_name}' in '{ns}'")
                        except Exception as pod_err:
                            kubeguard_pod_predictions_total.labels(namespace=ns, result="failure").inc()
                            logger.error(
                                f"Error evaluating pod '{pod_name}' in namespace '{ns}': {pod_err}",
                                extra={"namespace": ns, "pod": pod_name, "error_type": type(pod_err).__name__},
                            )

                    # 4. Clean up stale pod metrics
                    try:
                        cleanup_stale_metrics(active_pods)
                    except Exception as clean_err:
                        logger.error(f"Error executing stale metrics cleanup: {clean_err}")

                    # Mark successful cycle timestamp
                    self.last_success_timestamp = time.time()
                    kubeguard_worker_last_success_timestamp.set(self.last_success_timestamp)
                    kubeguard_worker_pods_evaluated.set(len(active_pods))
                    kubeguard_monitoring_cycle_duration_seconds.observe(time.time() - cycle_start)

                    # 5. Periodic model retraining check
                    now = time.time()
                    if (now - last_retrain_check) >= self.orchestrator.model_retrain_interval_seconds:
                        last_retrain_check = now
                        try:
                            sample_count = self.orchestrator.feature_store.count_features()
                            if sample_count >= self.orchestrator.min_training_samples:
                                logger.info(
                                    f"Retraining interval elapsed and {sample_count} samples available. "
                                    "Retraining historical Isolation Forest model..."
                                )
                                self.orchestrator.train_historical_model()
                        except Exception as retrain_err:
                            logger.error(f"Error during periodic model retraining: {retrain_err}")

                    # 6. Periodic retention cleanup (once every 6 hours)
                    if (now - last_retention_check) >= 21600:
                        last_retention_check = now
                        try:
                            self.orchestrator.feature_store.delete_old_features(self.retention_days)
                        except Exception as ret_err:
                            logger.error(f"Error purging old features: {ret_err}")

                else:
                    logger.warning("Anomaly detector is not fitted yet. Skipping scan iteration.")

            except Exception as cycle_err:
                cycle_failed = True
                kubeguard_monitoring_cycle_failures_total.inc()
                logger.error(f"Unhandled error during monitoring cycle iteration: {cycle_err}")

            # Update worker health gauge
            update_worker_health_metric(self.last_success_timestamp, self.health_timeout)

            # Wait for next cycle or stop event
            self._stop_event.wait(timeout=self.interval)


