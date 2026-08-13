"""kubeguard pods — display monitored pod risk scores from the KubeGuard metrics endpoint."""

from __future__ import annotations

import re
import sys
from typing import List, Optional

import typer

from kubeguard_cli import DEFAULT_NAMESPACE, DEFAULT_RELEASE
from kubeguard_cli.utils import helm, kubectl
from kubeguard_cli.utils.output import console, print_error, print_json, print_table, styled_risk
from kubeguard_cli.utils.portforward import PortForwardContext


# ---------------------------------------------------------------------------
# Prometheus text-format parser
# ---------------------------------------------------------------------------
_LINE_RE = re.compile(r'^(\w+)\{([^}]*)\}\s+([\d.e+-]+)')
_LABEL_RE = re.compile(r'(\w+)="([^"]+)"')


def _parse_metrics(text: str) -> List[dict]:
    """Parse Prometheus text format from /metrics.

    Returns a list of dicts: {namespace, pod, score, risk_level}.
    Reads kubeguard_pod_risk_score for the score and kubeguard_pod_risk_level
    (one-hot) for the level.
    """
    scores: dict = {}
    levels: dict = {}

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        match = _LINE_RE.match(line)
        if not match:
            continue

        metric_name, label_str, val_str = match.groups()
        labels = dict(_LABEL_RE.findall(label_str))

        ns = labels.get("exported_namespace") or labels.get("namespace")
        pod = labels.get("exported_pod") or labels.get("pod")

        if not ns or not pod:
            continue

        if metric_name == "kubeguard_pod_risk_score":
            scores[(ns, pod)] = int(float(val_str))
        elif metric_name == "kubeguard_pod_risk_level":
            level = labels.get("level")
            val = float(val_str)
            if level and val > 0:
                levels[(ns, pod)] = level

    result = []
    for (ns, pod), score in scores.items():
        level = levels.get((ns, pod), "UNKNOWN")
        result.append({"namespace": ns, "pod": pod, "risk_level": level, "risk_score": score})

    result.sort(key=lambda r: (-r["risk_score"], r["namespace"], r["pod"]))
    return result



# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

def pods(
    namespace: Optional[str] = typer.Option(
        None,
        "--namespace", "-n",
        help="Filter by pod namespace.",
    ),
    risk: Optional[str] = typer.Option(
        None,
        "--risk",
        help="Filter by risk level: low, medium, high.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show risk scores for all KubeGuard-monitored pods.

    Data is read from the KubeGuard /metrics endpoint (Prometheus text format).
    No risk calculations are performed by the CLI.
    """
    from kubeguard_cli.main import state
    context = state.context
    kg_ns = state.namespace
    rel = state.release

    # Check KubeGuard is installed
    if not helm.helm_release_exists(rel, kg_ns, context=context):
        console.print(
            f"\n[yellow]KubeGuard is not installed in namespace '{kg_ns}'.[/yellow]\n"
            "Run [bold cyan]kubeguard install[/bold cyan] to install.\n"
        )
        sys.exit(1)

    # Port-forward to /metrics
    try:
        import requests as _req
        with PortForwardContext(
            target=f"svc/{rel}",
            remote_port=8000,
            namespace=kg_ns,
            context=context,
            timeout=15,
        ) as base_url:
            try:
                resp = _req.get(f"{base_url}/metrics", timeout=10)
                resp.raise_for_status()
                raw = resp.text
            except Exception as e:
                print_error(f"Failed to fetch /metrics: {e}")
    except RuntimeError as e:
        print_error(str(e), hint=f"Check: kubectl get pods -n {kg_ns}")

    # Parse
    records = _parse_metrics(raw)

    # Filter
    if namespace:
        records = [r for r in records if r["namespace"] == namespace]
    if risk:
        records = [r for r in records if r["risk_level"].upper() == risk.upper()]

    if not records:
        filter_desc = []
        if namespace:
            filter_desc.append(f"namespace={namespace}")
        if risk:
            filter_desc.append(f"risk={risk}")
        msg = "No pods" + (f" matching {', '.join(filter_desc)}" if filter_desc else "")
        console.print(f"\n[dim]{msg}[/dim]\n")
        return

    if as_json:
        print_json(records)
        return

    # Table
    rows = [
        [
            r["namespace"],
            r["pod"],
            styled_risk(r["risk_level"]),
            str(r["risk_score"]),
        ]
        for r in records
    ]
    print_table(
        columns=["NAMESPACE", "POD", "RISK", "SCORE"],
        rows=rows,
        column_styles=["cyan", "white", "white", "bold white"],
    )
    console.print()
