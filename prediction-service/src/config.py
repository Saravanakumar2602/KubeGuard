"""Centralized configuration object for KubeGuard AI prediction service."""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger("kubeguard-config")

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
VALID_LOG_FORMATS = {"text", "json"}


@dataclass
class KubeGuardConfig:
    """Validated configuration for KubeGuard service environment variables."""

    prometheus_url: str = field(
        default_factory=lambda: os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
    )
    monitor_namespaces: List[str] = field(default_factory=list)
    monitor_interval_seconds: float = 30.0
    feature_store_path: str = field(
        default_factory=lambda: os.environ.get("FEATURE_STORE_PATH", "/data/kubeguard.db")
    )
    feature_retention_days: int = 7
    model_path: str = field(
        default_factory=lambda: os.environ.get("MODEL_PATH", "/data/kubeguard-isolation-forest.joblib")
    )
    min_training_samples: int = 50
    model_retrain_interval_seconds: float = 3600.0
    log_level: str = "INFO"
    log_format: str = "text"
    worker_health_timeout_seconds: float = 90.0
    alertmanager_url: str = field(
        default_factory=lambda: os.environ.get(
            "ALERTMANAGER_URL", "http://kube-prometheus-stack-alertmanager.monitoring.svc:9093"
        )
    )
    incident_resolution_grace_seconds: float = 120.0
    incident_retention_days: int = 30

    @classmethod
    def from_env(cls) -> KubeGuardConfig:
        """Construct and validate KubeGuardConfig from process environment variables."""
        # 1. Namespaces
        raw_ns = os.environ.get("MONITOR_NAMESPACES", "demo,kubeguard-test")
        namespaces = [ns.strip() for ns in raw_ns.split(",") if ns.strip()]
        if not namespaces:
            namespaces = ["demo"]

        # 2. Monitor interval
        raw_interval = os.environ.get("MONITOR_INTERVAL_SECONDS", "30")
        try:
            monitor_interval = float(raw_interval)
            if monitor_interval <= 0:
                raise ValueError
        except ValueError:
            raise ValueError(f"Invalid MONITOR_INTERVAL_SECONDS value '{raw_interval}'. Must be a positive number.")

        # 3. Retention days
        raw_retention = os.environ.get("FEATURE_RETENTION_DAYS", "7")
        try:
            retention_days = int(raw_retention)
            if retention_days < 1:
                raise ValueError
        except ValueError:
            raise ValueError(f"Invalid FEATURE_RETENTION_DAYS value '{raw_retention}'. Must be an integer >= 1.")

        # 4. Min training samples
        raw_min_samples = os.environ.get("MIN_TRAINING_SAMPLES", "50")
        try:
            min_samples = int(raw_min_samples)
            if min_samples < 1:
                raise ValueError
        except ValueError:
            raise ValueError(f"Invalid MIN_TRAINING_SAMPLES value '{raw_min_samples}'. Must be an integer >= 1.")

        # 5. Model retrain interval
        raw_retrain_int = os.environ.get("MODEL_RETRAIN_INTERVAL_SECONDS", "3600")
        try:
            retrain_interval = float(raw_retrain_int)
            if retrain_interval <= 0:
                raise ValueError
        except ValueError:
            raise ValueError(
                f"Invalid MODEL_RETRAIN_INTERVAL_SECONDS value '{raw_retrain_int}'. Must be a positive number."
            )

        # 6. Log level
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        if log_level not in VALID_LOG_LEVELS:
            raise ValueError(
                f"Invalid LOG_LEVEL '{log_level}'. Must be one of {sorted(list(VALID_LOG_LEVELS))}."
            )

        # 7. Log format
        log_format = os.environ.get("LOG_FORMAT", "text").lower()
        if log_format not in VALID_LOG_FORMATS:
            raise ValueError(
                f"Invalid LOG_FORMAT '{log_format}'. Must be one of {sorted(list(VALID_LOG_FORMATS))}."
            )

        # 8. Worker health timeout
        raw_timeout = os.environ.get("WORKER_HEALTH_TIMEOUT_SECONDS", "90")
        try:
            health_timeout = float(raw_timeout)
            if health_timeout <= 0:
                raise ValueError
        except ValueError:
            raise ValueError(
                f"Invalid WORKER_HEALTH_TIMEOUT_SECONDS value '{raw_timeout}'. Must be a positive number."
            )

        # 9. Incident resolution grace seconds
        raw_grace = os.environ.get("INCIDENT_RESOLUTION_GRACE_SECONDS", "120")
        try:
            grace_seconds = float(raw_grace)
            if grace_seconds < 0:
                raise ValueError
        except ValueError:
            raise ValueError(
                f"Invalid INCIDENT_RESOLUTION_GRACE_SECONDS value '{raw_grace}'. Must be a non-negative number."
            )

        # 10. Incident retention days
        raw_inc_retention = os.environ.get("INCIDENT_RETENTION_DAYS", "30")
        try:
            inc_retention = int(raw_inc_retention)
            if inc_retention < 1:
                raise ValueError
        except ValueError:
            raise ValueError(
                f"Invalid INCIDENT_RETENTION_DAYS value '{raw_inc_retention}'. Must be an integer >= 1."
            )

        return cls(
            prometheus_url=os.environ.get("PROMETHEUS_URL", "http://localhost:9090"),
            monitor_namespaces=namespaces,
            monitor_interval_seconds=monitor_interval,
            feature_store_path=os.environ.get("FEATURE_STORE_PATH", "/data/kubeguard.db"),
            feature_retention_days=retention_days,
            model_path=os.environ.get("MODEL_PATH", "/data/kubeguard-isolation-forest.joblib"),
            min_training_samples=min_samples,
            model_retrain_interval_seconds=retrain_interval,
            log_level=log_level,
            log_format=log_format,
            worker_health_timeout_seconds=health_timeout,
            alertmanager_url=os.environ.get(
                "ALERTMANAGER_URL", "http://kube-prometheus-stack-alertmanager.monitoring.svc:9093"
            ),
            incident_resolution_grace_seconds=grace_seconds,
            incident_retention_days=inc_retention,
        )

    def log_summary(self, target_logger: logging.Logger = logger) -> None:
        """Log a safe, non-sensitive summary of application configuration."""
        target_logger.info("KubeGuard Configuration Summary:")
        target_logger.info(f"  Prometheus URL           : {self.prometheus_url}")
        target_logger.info(f"  Alertmanager URL         : {self.alertmanager_url}")
        target_logger.info(f"  Monitoring Interval      : {self.monitor_interval_seconds}s")
        target_logger.info(f"  Monitoring Namespaces    : {','.join(self.monitor_namespaces)}")
        target_logger.info(f"  Feature Store Path       : {self.feature_store_path}")
        target_logger.info(f"  Feature Retention Days   : {self.feature_retention_days} days")
        target_logger.info(f"  Model Path               : {self.model_path}")
        target_logger.info(f"  Minimum Training Samples : {self.min_training_samples}")
        target_logger.info(f"  Model Retrain Interval   : {self.model_retrain_interval_seconds}s")
        target_logger.info(f"  Incident Grace Period    : {self.incident_resolution_grace_seconds}s")
        target_logger.info(f"  Incident Retention       : {self.incident_retention_days} days")
        target_logger.info(f"  Log Level / Format       : {self.log_level} / {self.log_format}")
        target_logger.info(f"  Worker Health Timeout    : {self.worker_health_timeout_seconds}s")

