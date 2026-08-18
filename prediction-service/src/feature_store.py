"""SQLite-backed historical feature store for KubeGuard pod telemetry observations."""

from __future__ import annotations

import os
import sys
import time
import sqlite3
import logging
import threading
from typing import List, Optional, Tuple

logger = logging.getLogger("kubeguard-feature-store")

# Resolve path to import PodFeatures
current_dir = os.path.dirname(os.path.abspath(__file__))
feature_src = os.path.abspath(os.path.join(current_dir, "../../feature-service/src"))
if feature_src not in sys.path:
    sys.path.append(feature_src)

from feature_service import PodFeatures
from contextlib import contextmanager

from metrics import (
    kubeguard_feature_store_observations_total,
    kubeguard_feature_store_errors_total,
    kubeguard_feature_store_records,
)


class FeatureStore:
    """Repository for persistent storage of pod feature observations using SQLite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize FeatureStore with database path.

        Args:
            db_path: Path to SQLite database file. Defaults to FEATURE_STORE_PATH env var
                     or '/data/kubeguard.db'.
        """
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = os.environ.get("FEATURE_STORE_PATH", "/data/kubeguard.db")

        self._lock = threading.Lock()
        self._initialize_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return a SQLite connection."""
        # Ensure parent directory exists
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.OperationalError as e:
            logger.warning(f"Could not set PRAGMA journal_mode=WAL: {e}")
        try:
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.execute("PRAGMA foreign_keys=ON;")
        except sqlite3.OperationalError as e:
            logger.warning(f"Could not set SQLite PRAGMAs: {e}")
        return conn

    @contextmanager
    def _connect(self):
        """Context manager yielding a SQLite connection that is explicitly closed upon exit."""
        conn = self._get_connection()
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _initialize_db(self) -> None:
        """Create database tables and indexes if they do not exist."""
        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS feature_observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        namespace TEXT NOT NULL,
                        pod TEXT NOT NULL,
                        cpu_current REAL,
                        cpu_average REAL,
                        cpu_max REAL,
                        cpu_min REAL,
                        cpu_trend REAL,
                        memory_current REAL,
                        memory_average REAL,
                        memory_max REAL,
                        memory_min REAL,
                        memory_trend REAL,
                        restart_count INTEGER
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ns_pod_ts ON feature_observations (namespace, pod, timestamp)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ts ON feature_observations (timestamp)"
                )
                conn.commit()
        try:
            kubeguard_feature_store_records.set(self.count_features())
        except Exception:
            pass
        logger.info(f"FeatureStore initialized at: {self.db_path}")


    def save_feature(self, f: PodFeatures, timestamp: Optional[float] = None) -> bool:
        """Save a single PodFeatures observation to SQLite.

        Args:
            f: The PodFeatures object to persist.
            timestamp: Observation timestamp (defaults to current time).

        Returns:
            True if saved, False if skipped due to invalid/incomplete data or duplicate window.
        """
        # Validate observation completeness
        if f.cpu_current is None or f.memory_current is None:
            logger.debug(f"Skipping storage for incomplete observation: {f.pod} in {f.namespace}")
            return False

        ts = timestamp if timestamp is not None else time.time()

        try:
            with self._lock:
                with self._connect() as conn:
                    cursor = conn.cursor()

                    # Deduplication: check if observation for same (ns, pod) exists within 5 seconds
                    cursor.execute(
                        """
                        SELECT id FROM feature_observations
                        WHERE namespace = ? AND pod = ? AND ABS(timestamp - ?) < 5.0
                        LIMIT 1
                        """,
                        (f.namespace, f.pod, ts),
                    )
                    if cursor.fetchone() is not None:
                        logger.debug(f"Skipping duplicate observation for pod '{f.pod}' in window.")
                        return False

                    cursor.execute(
                        """
                        INSERT INTO feature_observations (
                            timestamp, namespace, pod,
                            cpu_current, cpu_average, cpu_max, cpu_min, cpu_trend,
                            memory_current, memory_average, memory_max, memory_min, memory_trend,
                            restart_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ts,
                            f.namespace,
                            f.pod,
                            f.cpu_current,
                            f.cpu_average,
                            f.cpu_max,
                            f.cpu_min,
                            f.cpu_trend,
                            f.memory_current,
                            f.memory_average,
                            f.memory_max,
                            f.memory_min,
                            f.memory_trend,
                            f.restart_count,
                        ),
                    )
                    conn.commit()

            kubeguard_feature_store_observations_total.inc()
            kubeguard_feature_store_records.set(self.count_features())
            return True
        except Exception as e:
            kubeguard_feature_store_errors_total.inc()
            logger.error(f"Error persisting feature observation to SQLite: {e}")
            return False


    def count_features(self) -> int:
        """Return total count of feature observations in the database."""
        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM feature_observations")
                return cursor.fetchone()[0]

    def get_features(self, limit: Optional[int] = None) -> List[PodFeatures]:
        """Retrieve all stored feature observations as a list of PodFeatures objects."""
        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                query = "SELECT * FROM feature_observations ORDER BY timestamp ASC"
                if limit:
                    query += f" LIMIT {limit}"
                cursor.execute(query)
                rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append(
                PodFeatures(
                    pod=row["pod"],
                    namespace=row["namespace"],
                    cpu_current=row["cpu_current"],
                    cpu_average=row["cpu_average"],
                    cpu_max=row["cpu_max"],
                    cpu_min=row["cpu_min"],
                    cpu_trend=row["cpu_trend"],
                    memory_current=row["memory_current"],
                    memory_average=row["memory_average"],
                    memory_max=row["memory_max"],
                    memory_min=row["memory_min"],
                    memory_trend=row["memory_trend"],
                    restart_count=row["restart_count"] or 0,
                )
            )
        return results

    def get_recent_features(self, seconds: float = 3600.0) -> List[PodFeatures]:
        """Retrieve feature observations recorded within the last N seconds."""
        cutoff = time.time() - seconds
        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM feature_observations WHERE timestamp >= ? ORDER BY timestamp ASC",
                    (cutoff,),
                )
                rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append(
                PodFeatures(
                    pod=row["pod"],
                    namespace=row["namespace"],
                    cpu_current=row["cpu_current"],
                    cpu_average=row["cpu_average"],
                    cpu_max=row["cpu_max"],
                    cpu_min=row["cpu_min"],
                    cpu_trend=row["cpu_trend"],
                    memory_current=row["memory_current"],
                    memory_average=row["memory_average"],
                    memory_max=row["memory_max"],
                    memory_min=row["memory_min"],
                    memory_trend=row["memory_trend"],
                    restart_count=row["restart_count"] or 0,
                )
            )
        return results

    def delete_old_features(self, retention_days: int = 7) -> int:
        """Purge feature observations older than the retention period.

        Args:
            retention_days: Number of days of history to retain.

        Returns:
            Number of deleted records.
        """
        cutoff = time.time() - (retention_days * 86400)
        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM feature_observations WHERE timestamp < ?", (cutoff,))
                deleted = cursor.rowcount
                conn.commit()

        if deleted > 0:
            logger.info(f"Purged {deleted} historical feature observations older than {retention_days} days.")

        try:
            kubeguard_feature_store_records.set(self.count_features())
        except Exception:
            pass
        return deleted

