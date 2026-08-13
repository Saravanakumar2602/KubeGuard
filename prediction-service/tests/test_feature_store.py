"""Unit tests for SQLite FeatureStore."""

import os
import sys
import time
import tempfile
import pytest

current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "../src"))
if src_dir not in sys.path:
    sys.path.append(src_dir)

feature_src = os.path.abspath(os.path.join(current_dir, "../../feature-service/src"))
if feature_src not in sys.path:
    sys.path.append(feature_src)

from feature_store import FeatureStore
from feature_service import PodFeatures


import gc

@pytest.fixture
def temp_store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_db = f.name
    store = FeatureStore(db_path=tmp_db)
    yield store
    del store
    gc.collect()
    if os.path.exists(tmp_db):
        try:
            os.remove(tmp_db)
        except OSError:
            pass



def _make_pod_features(pod="nginx-1", ns="demo", cpu=0.05, mem=50.0):
    return PodFeatures(
        pod=pod,
        namespace=ns,
        cpu_current=cpu,
        cpu_average=cpu,
        cpu_max=cpu * 1.2,
        cpu_min=cpu * 0.8,
        cpu_trend=0.0001,
        memory_current=mem * 1024 * 1024,
        memory_average=mem * 1024 * 1024,
        memory_max=mem * 1.1 * 1024 * 1024,
        memory_min=mem * 0.9 * 1024 * 1024,
        memory_trend=10.0,
        restart_count=0,
    )


class TestFeatureStore:
    def test_database_initialization(self, temp_store):
        assert os.path.exists(temp_store.db_path)
        assert temp_store.count_features() == 0

    def test_save_and_count_feature(self, temp_store):
        pf = _make_pod_features()
        saved = temp_store.save_feature(pf)
        assert saved is True
        assert temp_store.count_features() == 1

    def test_deduplication_in_5s_window(self, temp_store):
        pf = _make_pod_features()
        now = time.time()
        assert temp_store.save_feature(pf, timestamp=now) is True
        # Immediate second save for same pod/ns within 5s window should return False
        assert temp_store.save_feature(pf, timestamp=now + 1.0) is False
        assert temp_store.count_features() == 1

    def test_get_features(self, temp_store):
        pf1 = _make_pod_features(pod="p1", ns="demo")
        pf2 = _make_pod_features(pod="p2", ns="test")
        now = time.time()
        temp_store.save_feature(pf1, timestamp=now)
        temp_store.save_feature(pf2, timestamp=now + 10.0)

        feats = temp_store.get_features()
        assert len(feats) == 2
        assert feats[0].pod == "p1"
        assert feats[1].pod == "p2"

    def test_get_recent_features(self, temp_store):
        pf1 = _make_pod_features(pod="p1")
        pf2 = _make_pod_features(pod="p2")
        now = time.time()

        temp_store.save_feature(pf1, timestamp=now - 7200.0)  # 2h ago
        temp_store.save_feature(pf2, timestamp=now - 60.0)    # 1m ago

        recent = temp_store.get_recent_features(seconds=3600) # last 1h
        assert len(recent) == 1
        assert recent[0].pod == "p2"

    def test_retention_purge(self, temp_store):
        pf1 = _make_pod_features(pod="old")
        pf2 = _make_pod_features(pod="new")
        now = time.time()

        temp_store.save_feature(pf1, timestamp=now - 10 * 86400) # 10 days ago
        temp_store.save_feature(pf2, timestamp=now)               # today

        assert temp_store.count_features() == 2
        deleted = temp_store.delete_old_features(retention_days=7)
        assert deleted == 1
        assert temp_store.count_features() == 1

        remaining = temp_store.get_features()
        assert remaining[0].pod == "new"

    def test_rejects_incomplete_observations(self, temp_store):
        incomplete = PodFeatures(
            pod="broken",
            namespace="demo",
            cpu_current=None,
            cpu_average=0.1,
            cpu_max=0.1,
            cpu_min=0.1,
            cpu_trend=0.0,
            memory_current=None,
            memory_average=100.0,
            memory_max=100.0,
            memory_min=100.0,
            memory_trend=0.0,
            restart_count=0,
        )
        assert temp_store.save_feature(incomplete) is False
        assert temp_store.count_features() == 0
