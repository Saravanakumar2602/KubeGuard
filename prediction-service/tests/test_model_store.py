"""Unit tests for joblib ModelStore."""

import os
import sys
import tempfile
import pytest
from sklearn.ensemble import IsolationForest

current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "../src"))
if src_dir not in sys.path:
    sys.path.append(src_dir)

from model_store import ModelStore


@pytest.fixture
def temp_model_store():
    with tempfile.TemporaryDirectory() as tmp_dir:
        model_path = os.path.join(tmp_dir, "test-model.joblib")
        store = ModelStore(model_path=model_path)
        yield store


def _fit_dummy_model():
    clf = IsolationForest(contamination=0.1, random_state=42)
    X = [[0.1 * i] * 11 for i in range(10)]
    clf.fit(X)
    return clf


class TestModelStore:
    def test_missing_model_exists_returns_false(self, temp_model_store):
        assert temp_model_store.exists() is False
        model, meta = temp_model_store.load_model()
        assert model is None
        assert meta is None

    def test_save_and_load_model(self, temp_model_store):
        clf = _fit_dummy_model()
        meta_saved = temp_model_store.save_model(
            clf, training_sample_count=10, model_source="historical", model_version=1
        )
        assert temp_model_store.exists() is True
        assert meta_saved["model_version"] == 1
        assert meta_saved["model_source"] == "historical"

        loaded_clf, loaded_meta = temp_model_store.load_model()
        assert loaded_clf is not None
        assert loaded_meta["model_version"] == 1
        assert loaded_meta["training_sample_count"] == 10

    def test_metadata_retrieval(self, temp_model_store):
        clf = _fit_dummy_model()
        temp_model_store.save_model(clf, training_sample_count=25, model_source="bootstrap")
        meta = temp_model_store.get_metadata()
        assert meta is not None
        assert meta["model_source"] == "bootstrap"
        assert meta["training_sample_count"] == 25

    def test_corrupted_model_file_handling(self, temp_model_store):
        # Create corrupted file
        with open(temp_model_store.model_path, "wb") as f:
            f.write(b"not a joblib file")

        assert temp_model_store.exists() is True
        model, meta = temp_model_store.load_model()
        assert model is None
        assert meta is None

    def test_incremental_versioning(self, temp_model_store):
        clf = _fit_dummy_model()
        meta1 = temp_model_store.save_model(clf, training_sample_count=10)
        assert meta1["model_version"] == 1

        meta2 = temp_model_store.save_model(clf, training_sample_count=20)
        assert meta2["model_version"] == 2
