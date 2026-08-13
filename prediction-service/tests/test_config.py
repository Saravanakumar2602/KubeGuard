"""Unit tests for KubeGuardConfig class and environment variable validation."""

import os
import pytest
from config import KubeGuardConfig


def test_config_defaults(monkeypatch):
    """Test default values when no environment variables are set."""
    monkeypatch.delenv("PROMETHEUS_URL", raising=False)
    monkeypatch.delenv("MONITOR_NAMESPACES", raising=False)
    monkeypatch.delenv("MONITOR_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("FEATURE_STORE_PATH", raising=False)
    monkeypatch.delenv("FEATURE_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("MODEL_PATH", raising=False)
    monkeypatch.delenv("MIN_TRAINING_SAMPLES", raising=False)
    monkeypatch.delenv("MODEL_RETRAIN_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.delenv("WORKER_HEALTH_TIMEOUT_SECONDS", raising=False)

    cfg = KubeGuardConfig.from_env()
    assert cfg.prometheus_url == "http://localhost:9090"
    assert cfg.monitor_namespaces == ["demo", "kubeguard-test"]
    assert cfg.monitor_interval_seconds == 30.0
    assert cfg.feature_store_path == "/data/kubeguard.db"
    assert cfg.feature_retention_days == 7
    assert cfg.model_path == "/data/kubeguard-isolation-forest.joblib"
    assert cfg.min_training_samples == 50
    assert cfg.model_retrain_interval_seconds == 3600.0
    assert cfg.log_level == "INFO"
    assert cfg.log_format == "text"
    assert cfg.worker_health_timeout_seconds == 90.0


def test_config_env_overrides(monkeypatch):
    """Test custom environment variable overrides."""
    monkeypatch.setenv("PROMETHEUS_URL", "http://prometheus:9090")
    monkeypatch.setenv("MONITOR_NAMESPACES", "prod-a, prod-b ")
    monkeypatch.setenv("MONITOR_INTERVAL_SECONDS", "15")
    monkeypatch.setenv("FEATURE_STORE_PATH", "/tmp/custom.db")
    monkeypatch.setenv("FEATURE_RETENTION_DAYS", "14")
    monkeypatch.setenv("MODEL_PATH", "/tmp/custom.joblib")
    monkeypatch.setenv("MIN_TRAINING_SAMPLES", "100")
    monkeypatch.setenv("MODEL_RETRAIN_INTERVAL_SECONDS", "1800")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("LOG_FORMAT", "JSON")
    monkeypatch.setenv("WORKER_HEALTH_TIMEOUT_SECONDS", "60")

    cfg = KubeGuardConfig.from_env()
    assert cfg.prometheus_url == "http://prometheus:9090"
    assert cfg.monitor_namespaces == ["prod-a", "prod-b"]
    assert cfg.monitor_interval_seconds == 15.0
    assert cfg.feature_store_path == "/tmp/custom.db"
    assert cfg.feature_retention_days == 14
    assert cfg.model_path == "/tmp/custom.joblib"
    assert cfg.min_training_samples == 100
    assert cfg.model_retrain_interval_seconds == 1800.0
    assert cfg.log_level == "DEBUG"
    assert cfg.log_format == "json"
    assert cfg.worker_health_timeout_seconds == 60.0


def test_invalid_interval(monkeypatch):
    """Test invalid MONITOR_INTERVAL_SECONDS values."""
    monkeypatch.setenv("MONITOR_INTERVAL_SECONDS", "-10")
    with pytest.raises(ValueError, match="MONITOR_INTERVAL_SECONDS"):
        KubeGuardConfig.from_env()


def test_invalid_retention(monkeypatch):
    """Test invalid FEATURE_RETENTION_DAYS values."""
    monkeypatch.setenv("FEATURE_RETENTION_DAYS", "abc")
    with pytest.raises(ValueError, match="FEATURE_RETENTION_DAYS"):
        KubeGuardConfig.from_env()


def test_invalid_log_level(monkeypatch):
    """Test invalid LOG_LEVEL values."""
    monkeypatch.setenv("LOG_LEVEL", "TRACE")
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        KubeGuardConfig.from_env()


def test_invalid_log_format(monkeypatch):
    """Test invalid LOG_FORMAT values."""
    monkeypatch.setenv("LOG_FORMAT", "yaml")
    with pytest.raises(ValueError, match="LOG_FORMAT"):
        KubeGuardConfig.from_env()
