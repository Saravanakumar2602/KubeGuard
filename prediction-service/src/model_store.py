"""Model persistence layer for Isolation Forest artifacts using joblib."""

from __future__ import annotations

import os
import sys
import time
import logging
import threading
from typing import Any, Dict, Optional, Tuple

import joblib
from sklearn.ensemble import IsolationForest

logger = logging.getLogger("kubeguard-model-store")

DEFAULT_FEATURE_NAMES = [
    "cpu_current",
    "cpu_average",
    "cpu_max",
    "cpu_min",
    "cpu_trend",
    "memory_current",
    "memory_average",
    "memory_max",
    "memory_min",
    "memory_trend",
    "restart_count",
]


from metrics import kubeguard_model_load_total


class ModelStore:
    """Manages model artifact serialization, loading, and metadata tracking."""

    def __init__(self, model_path: Optional[str] = None) -> None:
        """Initialize ModelStore.

        Args:
            model_path: Path to serialized model file (.joblib). Defaults to MODEL_PATH
                        env var or '/data/kubeguard-isolation-forest.joblib'.
        """
        if model_path:
            self.model_path = model_path
        else:
            self.model_path = os.environ.get(
                "MODEL_PATH", "/data/kubeguard-isolation-forest.joblib"
            )

        self.meta_path = self.model_path + ".json"
        self._lock = threading.Lock()

    def exists(self) -> bool:
        """Return True if a serialized model artifact exists on disk."""
        return os.path.exists(self.model_path)

    def save_model(
        self,
        model: IsolationForest,
        training_sample_count: int,
        model_source: str = "historical",
        model_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Serialize model artifact and metadata to disk.

        Args:
            model: Fitted IsolationForest scikit-learn model object.
            training_sample_count: Number of observations used to fit the model.
            model_source: Source of training data ('bootstrap' or 'historical').
            model_version: Explicit model generation version number.

        Returns:
            The metadata dictionary saved alongside the model artifact.
        """
        with self._lock:
            # Ensure parent directory exists
            model_dir = os.path.dirname(os.path.abspath(self.model_path))
            if model_dir and not os.path.exists(model_dir):
                os.makedirs(model_dir, exist_ok=True)

            # Determine next version
            existing_meta = self._read_metadata_file()
            if model_version is not None:
                version = model_version
            elif existing_meta and "model_version" in existing_meta:
                version = existing_meta["model_version"] + 1
            else:
                version = 1

            metadata = {
                "model_version": version,
                "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "trained_at_timestamp": time.time(),
                "training_sample_count": training_sample_count,
                "model_source": model_source,
                "contamination": getattr(model, "contamination", "auto"),
                "random_state": getattr(model, "random_state", 42),
                "feature_names": DEFAULT_FEATURE_NAMES,
            }

            payload = {
                "model": model,
                "metadata": metadata,
            }

            # Atomic save via joblib
            joblib.dump(payload, self.model_path)
            logger.info(
                f"Saved model (version {version}, source={model_source}, samples={training_sample_count}) to {self.model_path}"
            )
            return metadata

    def load_model(self) -> Tuple[Optional[IsolationForest], Optional[Dict[str, Any]]]:
        """Load serialized model and metadata from disk.

        Returns:
            Tuple of (IsolationForest model object, metadata dict). Returns (None, None) if missing or invalid.
        """
        if not self.exists():
            kubeguard_model_load_total.labels(result="missing").inc()
            return None, None

        with self._lock:
            try:
                payload = joblib.load(self.model_path)
                if isinstance(payload, dict) and "model" in payload and "metadata" in payload:
                    logger.info(
                        f"Loaded persisted model from {self.model_path} "
                        f"(version={payload['metadata'].get('model_version')}, source={payload['metadata'].get('model_source')})"
                    )
                    kubeguard_model_load_total.labels(result="success").inc()
                    return payload["model"], payload["metadata"]
                else:
                    logger.warning(f"Corrupted model file structure at {self.model_path}")
                    kubeguard_model_load_total.labels(result="failure").inc()
                    return None, None
            except Exception as e:
                logger.error(f"Error loading model artifact from {self.model_path}: {e}")
                kubeguard_model_load_total.labels(result="failure").inc()
                return None, None


    def get_metadata(self) -> Optional[Dict[str, Any]]:
        """Read model metadata without deserializing full model pipeline."""
        _, meta = self.load_model()
        return meta

    def _read_metadata_file(self) -> Optional[Dict[str, Any]]:
        if not self.exists():
            return None
        try:
            payload = joblib.load(self.model_path)
            if isinstance(payload, dict):
                return payload.get("metadata")
        except Exception:
            pass
        return None
