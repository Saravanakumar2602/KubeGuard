"""SQLite-backed Incident Store for KubeGuard AI event correlation and history."""

from __future__ import annotations

import os
import sys
import time
import sqlite3
import logging
import threading
from contextlib import contextmanager
from typing import List, Optional, Tuple

logger = logging.getLogger("kubeguard-incident-store")

# Resolve paths to import Incident
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from incident import Incident, Signal, TimelineEvent, CorrelatedAlert


class IncidentStore:
    """Repository layer for persistent storage of incidents, signals, timeline events, and alerts using SQLite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = os.environ.get("FEATURE_STORE_PATH", "/data/kubeguard.db")

        self._lock = threading.Lock()
        self._initialize_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connect(self):
        conn = self._get_connection()
        try:
            yield conn
        finally:
            conn.close()

    def _initialize_db(self) -> None:
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                # 1. Incidents master table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS incidents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        incident_id TEXT UNIQUE NOT NULL,
                        namespace TEXT NOT NULL,
                        pod TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        status TEXT NOT NULL,
                        risk_level TEXT NOT NULL,
                        risk_score INTEGER NOT NULL,
                        recommendation TEXT NOT NULL
                    )
                    """
                )
                # 2. Incident Signals table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS incident_signals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        incident_id TEXT NOT NULL,
                        signal_name TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        value TEXT,
                        description TEXT,
                        detected_at TEXT NOT NULL,
                        FOREIGN KEY(incident_id) REFERENCES incidents(incident_id) ON DELETE CASCADE
                    )
                    """
                )
                # 3. Incident Timeline Events table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS incident_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        incident_id TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        description TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        FOREIGN KEY(incident_id) REFERENCES incidents(incident_id) ON DELETE CASCADE
                    )
                    """
                )
                # 4. Incident Correlated Alerts table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS incident_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        incident_id TEXT NOT NULL,
                        alert_name TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        fired_at TEXT NOT NULL,
                        resolved_at TEXT,
                        FOREIGN KEY(incident_id) REFERENCES incidents(incident_id) ON DELETE CASCADE
                    )
                    """
                )
                # Indexes
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_inc_id ON incidents (incident_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_inc_ns_pod_status ON incidents (namespace, pod, status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_inc_status ON incidents (status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_inc ON incident_events (incident_id)")
                conn.commit()
        logger.info(f"IncidentStore initialized at: {self.db_path}")

    def create_incident(self, incident: Incident) -> Incident:
        """Create and store a new Incident record with signals, timeline events, and alerts."""
        now = time.time()
        created_ts = now
        updated_ts = now

        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO incidents (
                        incident_id, namespace, pod, created_at, updated_at,
                        status, risk_level, risk_score, recommendation
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        incident.incident_id,
                        incident.namespace,
                        incident.pod,
                        created_ts,
                        updated_ts,
                        incident.status,
                        incident.risk_level,
                        incident.risk_score,
                        incident.recommendation,
                    ),
                )
                self._save_incident_child_records(cursor, incident)
                conn.commit()

        logger.info(f"Created incident '{incident.incident_id}' for pod '{incident.pod}' in '{incident.namespace}'.")
        return incident

    def update_incident(self, incident: Incident) -> Incident:
        """Update an existing Incident record and refresh signals, timeline events, and alerts."""
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE incidents SET
                        updated_at = ?,
                        status = ?,
                        risk_level = ?,
                        risk_score = ?,
                        recommendation = ?
                    WHERE incident_id = ?
                    """,
                    (
                        now,
                        incident.status,
                        incident.risk_level,
                        incident.risk_score,
                        incident.recommendation,
                        incident.incident_id,
                    ),
                )
                # Re-sync child records
                cursor.execute("DELETE FROM incident_signals WHERE incident_id = ?", (incident.incident_id,))
                cursor.execute("DELETE FROM incident_events WHERE incident_id = ?", (incident.incident_id,))
                cursor.execute("DELETE FROM incident_alerts WHERE incident_id = ?", (incident.incident_id,))
                self._save_incident_child_records(cursor, incident)
                conn.commit()

        return incident

    def _save_incident_child_records(self, cursor: sqlite3.Cursor, incident: Incident) -> None:
        for s in incident.signals:
            cursor.execute(
                """
                INSERT INTO incident_signals (incident_id, signal_name, severity, value, description, detected_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (incident.incident_id, s.signal_name, s.severity, s.value, s.description, s.detected_at),
            )
        for t in incident.timeline:
            cursor.execute(
                """
                INSERT INTO incident_events (incident_id, timestamp, event_type, description, severity)
                VALUES (?, ?, ?, ?, ?)
                """,
                (incident.incident_id, t.timestamp, t.event_type, t.description, t.severity),
            )
        for a in incident.alerts:
            cursor.execute(
                """
                INSERT INTO incident_alerts (incident_id, alert_name, severity, fired_at, resolved_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (incident.incident_id, a.alert_name, a.severity, a.fired_at, a.resolved_at),
            )

    def resolve_incident(self, incident_id: str) -> bool:
        """Transition an active incident status to 'resolved'."""
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE incidents SET status = 'resolved', updated_at = ? WHERE incident_id = ? AND status = 'active'",
                    (now, incident_id),
                )
                conn.commit()
                return cursor.rowcount > 0

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Fetch a single Incident by incident_id with full signals, timeline, and alerts."""
        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM incidents WHERE incident_id = ? LIMIT 1", (incident_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                return self._hydrate_incident(conn, row)

    def get_active_incident_for_pod(self, namespace: str, pod: str) -> Optional[Incident]:
        """Fetch the currently active Incident for a (namespace, pod) pair if one exists."""
        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT * FROM incidents
                    WHERE namespace = ? AND pod = ? AND status = 'active'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (namespace, pod),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return self._hydrate_incident(conn, row)

    def get_incidents(
        self,
        namespace: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Incident]:
        """Query recent incidents with optional filtering by namespace and status."""
        query = "SELECT * FROM incidents WHERE 1=1"
        params = []

        if namespace:
            query += " AND namespace = ?"
            params.append(namespace)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
                incidents = []
                for row in rows:
                    incidents.append(self._hydrate_incident(conn, row))
                return incidents

    def _hydrate_incident(self, conn: sqlite3.Connection, row: sqlite3.Row) -> Incident:
        inc_id = row["incident_id"]
        cursor = conn.cursor()

        # Signals
        cursor.execute("SELECT * FROM incident_signals WHERE incident_id = ?", (inc_id,))
        s_rows = cursor.fetchall()
        signals = [
            Signal(
                signal_name=r["signal_name"],
                severity=r["severity"],
                value=r["value"] or "",
                description=r["description"] or "",
                detected_at=r["detected_at"],
            )
            for r in s_rows
        ]

        # Timeline
        cursor.execute("SELECT * FROM incident_events WHERE incident_id = ? ORDER BY id ASC", (inc_id,))
        t_rows = cursor.fetchall()
        timeline = [
            TimelineEvent(
                timestamp=r["timestamp"],
                event_type=r["event_type"],
                description=r["description"] or "",
                severity=r["severity"],
            )
            for r in t_rows
        ]

        # Alerts
        cursor.execute("SELECT * FROM incident_alerts WHERE incident_id = ?", (inc_id,))
        a_rows = cursor.fetchall()
        alerts = [
            CorrelatedAlert(
                alert_name=r["alert_name"],
                severity=r["severity"],
                fired_at=r["fired_at"],
                resolved_at=r["resolved_at"],
            )
            for r in a_rows
        ]

        # Convert created_at/updated_at float timestamps to ISO format if needed
        c_at = row["created_at"]
        u_at = row["updated_at"]
        c_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(c_at)) if isinstance(c_at, (int, float)) else str(c_at)
        u_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(u_at)) if isinstance(u_at, (int, float)) else str(u_at)

        return Incident(
            incident_id=inc_id,
            namespace=row["namespace"],
            pod=row["pod"],
            created_at=c_str,
            updated_at=u_str,
            status=row["status"],
            risk_level=row["risk_level"],
            risk_score=row["risk_score"],
            recommendation=row["recommendation"],
            signals=signals,
            timeline=timeline,
            alerts=alerts,
        )

    def delete_old_resolved_incidents(self, retention_days: int = 30) -> int:
        """Purge resolved incidents older than retention window. Active incidents are retained."""
        cutoff = time.time() - (retention_days * 86400)
        with self._lock:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM incidents WHERE status = 'resolved' AND updated_at < ?", (cutoff,))
                deleted = cursor.rowcount
                conn.commit()

        if deleted > 0:
            logger.info(f"Purged {deleted} resolved incidents older than {retention_days} days.")
        return deleted
