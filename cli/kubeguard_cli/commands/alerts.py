"""kubeguard alerts — display active KubeGuard alerts from Alertmanager."""

from __future__ import annotations

import sys
from typing import List, Optional

import typer

from kubeguard_cli import DEFAULT_ALERTMANAGER_NS, DEFAULT_ALERTMANAGER_SVC, DEFAULT_NAMESPACE, DEFAULT_RELEASE
from kubeguard_cli.utils import helm, kubectl
from kubeguard_cli.utils.output import console, print_error, print_json, print_table, styled_risk
from kubeguard_cli.utils.portforward import PortForwardContext


# ---------------------------------------------------------------------------
# Alert parsing
# ---------------------------------------------------------------------------

def _parse_alerts(raw: list) -> List[dict]:
    """Filter and normalise KubeGuard alerts from Alertmanager /api/v2/alerts."""
    results = []
    for alert in raw:
        labels = alert.get("labels", {})
        name = labels.get("alertname", "")
        if not name.startswith("KubeGuard"):
            continue
        results.append(
            {
                "alert": name,
                "namespace": labels.get("exported_namespace", labels.get("namespace", "—")),
                "pod": labels.get("exported_pod", labels.get("pod", "—")),
                "severity": labels.get("severity", "—"),
                "state": alert.get("status", {}).get("state", "—"),
                "started_at": alert.get("startsAt", "—"),
            }
        )
    results.sort(key=lambda r: r["alert"])
    return results


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

def alerts(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
    alertmanager_svc: str = typer.Option(
        DEFAULT_ALERTMANAGER_SVC,
        "--alertmanager-svc",
        help="Alertmanager service name.",
    ),
    alertmanager_ns: str = typer.Option(
        DEFAULT_ALERTMANAGER_NS,
        "--alertmanager-ns",
        help="Namespace containing the Alertmanager service.",
    ),
) -> None:
    """Show active KubeGuard alerts from Alertmanager.

    Only alerts whose alertname begins with 'KubeGuard' are shown.
    Data comes from the Alertmanager /api/v2/alerts endpoint — no alert
    evaluation is performed by the CLI.
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

    # Check Alertmanager service exists
    am_svc = kubectl.get_service(alertmanager_svc, alertmanager_ns, context=context)
    if not am_svc:
        print_error(
            f"Alertmanager service '{alertmanager_svc}' not found in namespace '{alertmanager_ns}'.",
            hint="Pass --alertmanager-svc and --alertmanager-ns if using a different stack name.",
        )

    # Port-forward to Alertmanager
    try:
        import requests as _req
        with PortForwardContext(
            target=f"svc/{alertmanager_svc}",
            remote_port=9093,
            namespace=alertmanager_ns,
            context=context,
            timeout=15,
        ) as base_url:
            try:
                resp = _req.get(f"{base_url}/api/v2/alerts", timeout=10)
                resp.raise_for_status()
                raw = resp.json()
            except Exception as e:
                print_error(f"Failed to fetch alerts from Alertmanager: {e}")
    except RuntimeError as e:
        print_error(str(e), hint=f"Check: kubectl get svc -n {alertmanager_ns}")

    # Parse KubeGuard alerts
    parsed = _parse_alerts(raw)

    if not parsed:
        console.print("\n[bold green]No active KubeGuard alerts.[/bold green]\n")
        return

    if as_json:
        print_json(parsed)
        return

    rows = [
        [
            r["alert"],
            r["namespace"],
            r["pod"],
            r["severity"].upper(),
        ]
        for r in parsed
    ]
    print_table(
        columns=["ALERT", "NAMESPACE", "POD", "SEVERITY"],
        rows=rows,
        column_styles=["bold yellow", "cyan", "white", "bold red"],
    )
    console.print(f"[dim]  {len(parsed)} active alert(s)[/dim]\n")
