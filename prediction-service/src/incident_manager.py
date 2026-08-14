"""Incident Manager to correlate risk signals, track timeline events, and query Alertmanager."""

from __future__ import annotations

import os
import sys
import time
import logging
import requests
from typing import List, Dict, Optional, Set, Tuple

logger = logging.getLogger("kubeguard-incident-manager")

# Resolve paths
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

feature_src = os.path.abspath(os.path.join(current_dir, "../../feature-service/src"))
if feature_src not in sys.path:
    sys.path.append(feature_src)

from feature_service import PodFeatures
from anomaly_detector import AnomalyResult
from rule_engine import RiskResult
from incident import Incident, Signal, TimelineEvent, CorrelatedAlert
from incident_store import IncidentStore
from metrics import (
    kubeguard_incidents_created_total,
    kubeguard_incidents_resolved_total,
    kubeguard_active_incidents,
    kubeguard_incident_duration_seconds,
)


class IncidentManager:
    """Coordinates risk signal processing, timeline event generation, and Alertmanager alert correlation."""

    def __init__(
        self,
        incident_store: IncidentStore,
        alertmanager_url: str = "http://kube-prometheus-stack-alertmanager.monitoring.svc:9093",
        resolution_grace_seconds: float = 120.0,
        retention_days: int = 30,
    ) -> None:
        self.incident_store = incident_store
        self.alertmanager_url = alertmanager_url.rstrip("/")
        self.resolution_grace_seconds = resolution_grace_seconds
        self.retention_days = retention_days

        # In-memory tracking for grace-period resolution timestamps: (ns, pod) -> last_seen_signal_ts
        self._last_signal_seen: Dict[Tuple[str, str], float] = {}

    def process_assessment(
        self,
        features: PodFeatures,
        anomaly: AnomalyResult | None,
        risk: RiskResult,
    ) -> Optional[Incident]:
        """Process a pod's risk assessment, creating, updating, or resolving an incident.

        Args:
            features: PodFeatures calculated metrics.
            anomaly: AnomalyResult from Isolation Forest model.
            risk: RiskResult from Rule Engine.

        Returns:
            The created, updated, or active Incident object, or None if no incident is active.
        """
        now = time.time()
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
        key = (features.namespace, features.pod)

        # 1. Extract active signals
        active_signals = self._extract_signals(features, anomaly, risk, now_str)
        has_meaningful_risk = (
            (risk.risk_level in ["MEDIUM", "HIGH"])
            or (anomaly is not None and anomaly.is_anomaly)
            or (len(active_signals) > 0)
        )


        if has_meaningful_risk:
            self._last_signal_seen[key] = now

        # 2. Fetch existing active incident for pod
        active_inc = self.incident_store.get_active_incident_for_pod(features.namespace, features.pod)

        # 3. Case A: No active incident and meaningful risk exists -> Create new Incident
        if active_inc is None and has_meaningful_risk:
            inc_id = f"{features.namespace}/{features.pod}/{int(now)}"
            timeline = [
                TimelineEvent(
                    timestamp=now_str,
                    event_type="incident_created",
                    description=f"Incident created for pod '{features.pod}' in namespace '{features.namespace}'",
                    severity=risk.risk_level.lower(),
                ),
                TimelineEvent(
                    timestamp=now_str,
                    event_type="risk_detected",
                    description=f"Risk level assessed at {risk.risk_level} (score: {risk.risk_score})",
                    severity=risk.risk_level.lower(),
                ),
            ]
            for s in active_signals:
                event_type = f"{s.signal_name}_detected"
                timeline.append(
                    TimelineEvent(
                        timestamp=now_str,
                        event_type=event_type,
                        description=s.description,
                        severity=s.severity.lower(),
                    )
                )

            inc = Incident(
                incident_id=inc_id,
                namespace=features.namespace,
                pod=features.pod,
                created_at=now_str,
                updated_at=now_str,
                status="active",
                risk_level=risk.risk_level,
                risk_score=risk.risk_score,
                recommendation=risk.recommendation,
                signals=active_signals,
                timeline=timeline,
                alerts=[],
            )
            saved = self.incident_store.create_incident(inc)
            kubeguard_incidents_created_total.inc()
            self._update_active_incident_metrics()
            return saved

        # 4. Case B: Active incident exists and meaningful risk continues -> Update Incident
        if active_inc is not None and has_meaningful_risk:
            # Check state transitions to emit new timeline events
            prev_signal_names = {s.signal_name for s in active_inc.signals}

            # Risk level change
            if risk.risk_level != active_inc.risk_level:
                event_type = "risk_escalated" if self._risk_rank(risk.risk_level) > self._risk_rank(active_inc.risk_level) else "risk_deescalated"
                active_inc.timeline.append(
                    TimelineEvent(
                        timestamp=now_str,
                        event_type=event_type,
                        description=f"Risk level changed from {active_inc.risk_level} to {risk.risk_level} (score: {risk.risk_score})",
                        severity=risk.risk_level.lower(),
                    )
                )

            # New signal detected
            for s in active_signals:
                if s.signal_name not in prev_signal_names:
                    active_inc.timeline.append(
                        TimelineEvent(
                            timestamp=now_str,
                            event_type=f"{s.signal_name}_detected",
                            description=s.description,
                            severity=s.severity.lower(),
                        )
                    )

            active_inc.risk_level = risk.risk_level
            active_inc.risk_score = risk.risk_score
            active_inc.recommendation = risk.recommendation
            active_inc.signals = active_signals
            active_inc.updated_at = now_str

            updated = self.incident_store.update_incident(active_inc)
            self._update_active_incident_metrics()
            return updated

        # 5. Case C: Active incident exists but signals have cleared -> Resolve after grace period
        if active_inc is not None and not has_meaningful_risk:
            last_seen = self._last_signal_seen.get(key, now)
            if (now - last_seen) >= self.resolution_grace_seconds:
                active_inc.status = "resolved"
                active_inc.updated_at = now_str
                active_inc.timeline.append(
                    TimelineEvent(
                        timestamp=now_str,
                        event_type="incident_resolved",
                        description="All monitored risk signals have cleared and returned to normal baseline",
                        severity="info",
                    )
                )
                self.incident_store.update_incident(active_inc)
                kubeguard_incidents_resolved_total.inc()
                self._update_active_incident_metrics()

                # Calculate duration
                try:
                    c_ts = time.mktime(time.strptime(active_inc.created_at, "%Y-%m-%dT%H:%M:%SZ"))
                    kubeguard_incident_duration_seconds.observe(max(0, now - c_ts))
                except Exception:
                    pass

                logger.info(f"Resolved incident '{active_inc.incident_id}' for pod '{features.pod}'.")
                self._last_signal_seen.pop(key, None)
                return active_inc
            else:
                # Still within grace period -> keep active
                return active_inc

        return None

    def correlate_alerts(self) -> None:
        """Fetch firing alerts from Alertmanager and correlate them with active incidents."""
        if not self.alertmanager_url:
            return

        try:
            resp = requests.get(f"{self.alertmanager_url}/api/v2/alerts", timeout=5)
            if not resp.ok:
                return
            firing_alerts = resp.json()
        except Exception as e:
            logger.warning(f"Alertmanager unavailable at {self.alertmanager_url}: {e}")
            return

        active_incidents = self.incident_store.get_incidents(status="active")
        if not active_incidents:
            return

        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        for inc in active_incidents:
            inc_alerts: List[CorrelatedAlert] = list(inc.alerts)
            existing_alert_names = {a.alert_name for a in inc_alerts if a.resolved_at is None}
            current_firing_for_pod: Set[str] = set()

            for item in firing_alerts:
                labels = item.get("labels", {})
                ns = labels.get("exported_namespace") or labels.get("namespace")
                pod = labels.get("exported_pod") or labels.get("pod")

                if ns == inc.namespace and pod == inc.pod:
                    alert_name = labels.get("alertname", "UnknownAlert")
                    severity = labels.get("severity", "warning")
                    current_firing_for_pod.add(alert_name)

                    if alert_name not in existing_alert_names:
                        inc_alerts.append(
                            CorrelatedAlert(
                                alert_name=alert_name,
                                severity=severity,
                                fired_at=item.get("startsAt", now_str),
                            )
                        )
                        inc.timeline.append(
                            TimelineEvent(
                                timestamp=now_str,
                                event_type="alert_fired",
                                description=f"Prometheus alert '{alert_name}' fired for pod",
                                severity=severity,
                            )
                        )

            # Mark resolved alerts
            for a in inc_alerts:
                if a.resolved_at is None and a.alert_name not in current_firing_for_pod:
                    a.resolved_at = now_str
                    inc.timeline.append(
                        TimelineEvent(
                            timestamp=now_str,
                            event_type="alert_resolved",
                            description=f"Prometheus alert '{a.alert_name}' resolved",
                            severity="info",
                        )
                    )

            inc.alerts = inc_alerts
            self.incident_store.update_incident(inc)

    def _extract_signals(
        self,
        features: PodFeatures,
        anomaly: AnomalyResult | None,
        risk: RiskResult,
        now_str: str,
    ) -> List[Signal]:
        signals = []
        # 1. ML Anomaly
        if anomaly is not None and anomaly.is_anomaly:
            signals.append(
                Signal(
                    signal_name="ml_anomaly",
                    severity="HIGH",
                    value=f"{anomaly.score:.4f}",
                    description="Unusual resource behavior detected by Isolation Forest model.",
                    detected_at=now_str,
                )
            )
        # 2. Memory Trend
        if features.memory_trend is not None and features.memory_trend > 1000.0:
            sev = "HIGH" if features.memory_trend > 5000.0 else "MEDIUM"
            signals.append(
                Signal(
                    signal_name="memory_growth",
                    severity=sev,
                    value=f"{features.memory_trend:.1f} B/s",
                    description=f"Memory usage is increasing significantly ({features.memory_trend:.1f} bytes/sec).",
                    detected_at=now_str,
                )
            )
        # 3. CPU Trend
        if features.cpu_trend is not None and features.cpu_trend > 0.0001:
            signals.append(
                Signal(
                    signal_name="cpu_trend",
                    severity="MEDIUM",
                    value=f"{features.cpu_trend:.6f} cores/s",
                    description=f"CPU usage is increasing significantly ({features.cpu_trend:.6f} cores/sec).",
                    detected_at=now_str,
                )
            )
        # 4. Restarts
        if features.restart_count is not None and features.restart_count >= 1:
            sev = "HIGH" if features.restart_count >= 4 else "MEDIUM"
            signals.append(
                Signal(
                    signal_name="restart_count",
                    severity=sev,
                    value=str(features.restart_count),
                    description=f"Pod has restarted {features.restart_count} times.",
                    detected_at=now_str,
                )
            )
        return signals

    def _risk_rank(self, level: str) -> int:
        ranks = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        return ranks.get(level.upper(), 1)

    def _update_active_incident_metrics(self) -> None:
        """Update active incidents gauge broken down by risk level."""
        active = self.incident_store.get_incidents(status="active")
        low = sum(1 for i in active if i.risk_level == "LOW")
        med = sum(1 for i in active if i.risk_level == "MEDIUM")
        high = sum(1 for i in active if i.risk_level == "HIGH")

        kubeguard_active_incidents.labels(risk_level="LOW").set(low)
        kubeguard_active_incidents.labels(risk_level="MEDIUM").set(med)
        kubeguard_active_incidents.labels(risk_level="HIGH").set(high)
