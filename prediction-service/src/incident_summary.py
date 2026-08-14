"""Deterministic operator summary generator for KubeGuard incidents."""

from __future__ import annotations

import sys
import os
from typing import Dict, Any

# Resolve paths
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from incident import Incident


def generate_incident_summary(incident: Incident) -> str:
    """Generate a concise, human-readable operator summary for an incident.

    Args:
        incident: The Incident context object.

    Returns:
        Deterministic summary string describing what happened, current risk, and recommendation.
    """
    if incident.status == "resolved":
        return (
            f"Incident {incident.incident_id} for pod '{incident.pod}' in namespace '{incident.namespace}' "
            "has resolved. All monitored risk signals have returned to normal baseline levels."
        )

    signals_desc = []
    for s in incident.signals:
        signals_desc.append(s.description)

    signal_text = " ".join(signals_desc) if signals_desc else "Unusual resource behavior detected."

    summary = (
        f"Pod '{incident.pod}' in namespace '{incident.namespace}' is currently at {incident.risk_level} risk "
        f"(score: {incident.risk_score}). {signal_text} {incident.recommendation}"
    )
    return summary
