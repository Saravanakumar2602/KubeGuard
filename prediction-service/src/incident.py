"""Incident domain model structures for KubeGuard AI event correlation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Signal:
    """Represents a specific metric or anomaly signal contributing to an incident."""
    signal_name: str
    severity: str  # LOW, MEDIUM, HIGH
    value: str
    description: str
    detected_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_name": self.signal_name,
            "severity": self.severity,
            "value": self.value,
            "description": self.description,
            "detected_at": self.detected_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Signal:
        return cls(
            signal_name=data.get("signal_name", "unknown"),
            severity=data.get("severity", "LOW"),
            value=str(data.get("value", "")),
            description=data.get("description", ""),
            detected_at=data.get("detected_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        )


@dataclass
class TimelineEvent:
    """Represents a chronological state transition or key event in an incident's lifecycle."""
    timestamp: str
    event_type: str
    description: str
    severity: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "description": self.description,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TimelineEvent:
        return cls(
            timestamp=data.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            event_type=data.get("event_type", "event"),
            description=data.get("description", ""),
            severity=data.get("severity", "info"),
        )


@dataclass
class CorrelatedAlert:
    """Represents a Prometheus / Alertmanager alert associated with an incident."""
    alert_name: str
    severity: str
    fired_at: str
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_name": self.alert_name,
            "severity": self.severity,
            "fired_at": self.fired_at,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CorrelatedAlert:
        return cls(
            alert_name=data.get("alert_name", "alert"),
            severity=data.get("severity", "warning"),
            fired_at=data.get("fired_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            resolved_at=data.get("resolved_at"),
        )


@dataclass
class Incident:
    """Represents a full operational incident context for a pod."""
    incident_id: str
    namespace: str
    pod: str
    created_at: str
    updated_at: str
    status: str  # active, resolved
    risk_level: str  # LOW, MEDIUM, HIGH
    risk_score: int
    recommendation: str
    signals: List[Signal] = field(default_factory=list)
    timeline: List[TimelineEvent] = field(default_factory=list)
    alerts: List[CorrelatedAlert] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "namespace": self.namespace,
            "pod": self.pod,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "recommendation": self.recommendation,
            "signals": [s.to_dict() for s in self.signals],
            "timeline": [t.to_dict() for t in self.timeline],
            "alerts": [a.to_dict() for a in self.alerts],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Incident:
        return cls(
            incident_id=data.get("incident_id", ""),
            namespace=data.get("namespace", ""),
            pod=data.get("pod", ""),
            created_at=data.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            updated_at=data.get("updated_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            status=data.get("status", "active"),
            risk_level=data.get("risk_level", "LOW"),
            risk_score=data.get("risk_score", 0),
            recommendation=data.get("recommendation", ""),
            signals=[Signal.from_dict(s) for s in data.get("signals", [])],
            timeline=[TimelineEvent.from_dict(t) for t in data.get("timeline", [])],
            alerts=[CorrelatedAlert.from_dict(a) for a in data.get("alerts", [])],
        )
