"""Unit tests for KubeGuard persistent model lifecycle & retraining policies."""

import os
import sys
import time
import tempfile
from unittest.mock import patch, MagicMock
import pytest

current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "../src"))
if src_dir not in sys.path:
    sys.path.append(src_dir)

feature_src = os.path.abspath(os.path.join(current_dir, "../../feature-service/src"))
if feature_src not in sys.path:
    sys.path.append(feature_src)

from api import PredictionOrchestrator
from feature_service import PodFeatures


import gc

@pytest.fixture
def temp_orchestrator():
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test.db")
    model_path = os.path.join(tmp_dir, "model.joblib")
    with (
        patch.dict(
            os.environ,
            {
                "FEATURE_STORE_PATH": db_path,
                "MODEL_PATH": model_path,
                "MIN_TRAINING_SAMPLES": "5",
                "MODEL_RETRAIN_INTERVAL_SECONDS": "3600",
            },
        ),
        patch("api.PrometheusClient"),
    ):
        orchestrator = PredictionOrchestrator()
        yield orchestrator
        del orchestrator
        gc.collect()

    import shutil
    try:
        shutil.rmtree(tmp_dir)
    except OSError:
        pass



def _make_sample_feature(i: int):
    return PodFeatures(
        pod=f"pod-{i}",
        namespace="demo",
        cpu_current=0.05 + (i * 0.001),
        cpu_average=0.05,
        cpu_max=0.08,
        cpu_min=0.02,
        cpu_trend=0.0001,
        memory_current=50.0 * 1024 * 1024 + (i * 1000),
        memory_average=50.0 * 1024 * 1024,
        memory_max=60.0 * 1024 * 1024,
        memory_min=40.0 * 1024 * 1024,
        memory_trend=10.0,
        restart_count=0,
    )


class TestModelLifecycle:
    def test_bootstrap_fallback_when_features_below_min_samples(self, temp_orchestrator):
        # Save only 2 features (threshold is 5)
        for i in range(2):
            temp_orchestrator.feature_store.save_feature(
                _make_sample_feature(i), timestamp=time.time() + i * 10
            )

        with patch.object(temp_orchestrator, "_train_bootstrap_model", return_value=True) as mock_boot:
            result = temp_orchestrator.initialize_model()
            assert result is True
            mock_boot.assert_called_once()

    def test_historical_training_when_features_equal_or_above_min_samples(self, temp_orchestrator):
        # Save 6 features (threshold is 5)
        for i in range(6):
            temp_orchestrator.feature_store.save_feature(
                _make_sample_feature(i), timestamp=time.time() + i * 10
            )

        result = temp_orchestrator.initialize_model()
        assert result is True
        assert temp_orchestrator.detector.is_fitted is True
        assert temp_orchestrator.detector.model_source == "historical"
        assert temp_orchestrator.detector.training_sample_count == 6

    def test_persisted_model_loads_on_reinitialization(self, temp_orchestrator):
        # Save 6 features and train
        for i in range(6):
            temp_orchestrator.feature_store.save_feature(
                _make_sample_feature(i), timestamp=time.time() + i * 10
            )
        temp_orchestrator.initialize_model()

        # Re-create detector in a fresh state to test load
        temp_orchestrator.detector.is_fitted = False
        temp_orchestrator.detector.model_source = "none"

        result = temp_orchestrator.initialize_model()
        assert result is True
        assert temp_orchestrator.detector.is_fitted is True
        assert temp_orchestrator.detector.model_source == "historical"
        assert temp_orchestrator.detector.model_version == 1

    def test_retraining_historical_model_increments_version(self, temp_orchestrator):
        for i in range(6):
            temp_orchestrator.feature_store.save_feature(
                _make_sample_feature(i), timestamp=time.time() + i * 10
            )
        temp_orchestrator.train_historical_model()
        assert temp_orchestrator.detector.model_version == 1

        # Add more features & retrain
        for i in range(6, 10):
            temp_orchestrator.feature_store.save_feature(
                _make_sample_feature(i), timestamp=time.time() + i * 10
            )
        temp_orchestrator.train_historical_model()
        assert temp_orchestrator.detector.model_version == 2
        assert temp_orchestrator.detector.training_sample_count == 10
