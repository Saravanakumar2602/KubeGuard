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

from metrics import cleanup_stale_metrics


class MonitoringWorker:
    """Background monitoring worker that discovers pods, evaluates predictions, and updates metrics."""

    def __init__(self, orchestrator) -> None:
        self.orchestrator = orchestrator

        # Read configurations
        interval_str = os.environ.get("MONITOR_INTERVAL_SECONDS", "60")
        try:
            self.interval = float(interval_str)
        except ValueError:
            logger.warning(f"Invalid MONITOR_INTERVAL_SECONDS value '{interval_str}', defaulting to 60.")
            self.interval = 60.0

        namespaces_str = os.environ.get("MONITOR_NAMESPACES", "demo")
        self.namespaces = [ns.strip() for ns in namespaces_str.split(",") if ns.strip()]

        self.retention_days = int(os.environ.get("FEATURE_RETENTION_DAYS", "7"))
        self._stop_event = threading.Event()
        self._thread = None

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
            logger.info("Starting periodic namespace metrics scan...")
            active_pods = []

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

                # 3. Evaluate each discovered pod
                for pod_name, ns in active_pods:
                    if self._stop_event.is_set():
                        break
                    logger.info(f"Evaluating pod '{pod_name}' in namespace '{ns}'...")
                    try:
                        # predict() will automatically compute features, save to FeatureStore, evaluate risk, and update Gauges
                        self.orchestrator.predict(namespace=ns, pod=pod_name)
                        logger.info(f"Metrics updated successfully for pod '{pod_name}' in '{ns}'")
                    except Exception as pod_err:
                        logger.error(f"Error evaluating pod '{pod_name}' in namespace '{ns}': {pod_err}")

                # 4. Clean up stale pod metrics
                try:
                    cleanup_stale_metrics(active_pods)
                except Exception as clean_err:
                    logger.error(f"Error executing stale metrics cleanup: {clean_err}")

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

            # Wait for next cycle or stop event
            self._stop_event.wait(timeout=self.interval)

