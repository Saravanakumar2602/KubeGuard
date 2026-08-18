"""kubeguard incidents — display correlated incident contexts from the KubeGuard API."""

from __future__ import annotations

import sys
from typing import List, Optional

import requests
import typer

from kubeguard_cli.utils import helm
from kubeguard_cli.utils.output import console, print_error, print_json, print_table, styled_risk, get_symbol
from kubeguard_cli.utils.portforward import PortForwardContext


def incidents(
    incident_id: Optional[str] = typer.Option(
        None,
        "--id",
        help="Fetch detailed context for a specific incident ID.",
    ),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        help="Filter incidents by status: active or resolved.",
    ),
    namespace: Optional[str] = typer.Option(
        None,
        "--namespace", "-n",
        help="Filter incidents by target namespace.",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        help="Maximum number of incidents to display.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Inspect correlated incident contexts, timelines, signals, and alerts."""
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

    # Fetch from API via port-forward
    try:
        with PortForwardContext(
            target=f"svc/{rel}",
            remote_port=8000,
            namespace=kg_ns,
            context=context,
            timeout=15,
        ) as base_url:
            if incident_id:
                # Detail view endpoint
                url = f"{base_url}/incidents/{incident_id}"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 404:
                    if as_json:
                        print_json({"error": "not_found", "incident_id": incident_id})
                    else:
                        console.print(f"\n[yellow]Incident '{incident_id}' not found.[/yellow]\n")
                    return
                resp.raise_for_status()
                data = resp.json()
                _render_incident_detail(data, as_json=as_json)
                return

            else:
                # Summary list endpoint
                params = {}
                if namespace:
                    params["namespace"] = namespace
                if status:
                    params["status"] = status.lower()
                params["limit"] = limit

                resp = requests.get(f"{base_url}/incidents", params=params, timeout=10)
                resp.raise_for_status()
                records = resp.json()
                _render_incidents_list(records, namespace=namespace, status=status, as_json=as_json)
                return

    except Exception as e:
        print_error(f"Failed to fetch incidents from KubeGuard API: {e}")


def _render_incidents_list(
    records: List[dict],
    namespace: Optional[str] = None,
    status: Optional[str] = None,
    as_json: bool = False,
) -> None:
    if as_json:
        print_json(records)
        return

    if not records:
        filter_desc = []
        if namespace:
            filter_desc.append(f"namespace={namespace}")
        if status:
            filter_desc.append(f"status={status}")
        msg = "No KubeGuard incidents" + (f" matching {', '.join(filter_desc)}" if filter_desc else "")
        console.print(f"\n[dim]{msg}[/dim]\n")
        return

    console.print("\n[bold cyan]KubeGuard Incidents[/bold cyan]")
    console.print("----------------------------------------", style="dim")

    rows = []
    for r in records:
        st = r.get("status", "active").upper()
        st_styled = f"[bold green]{st}[/bold green]" if st == "RESOLVED" else f"[bold yellow]{st}[/bold yellow]"
        risk_styled = styled_risk(r.get("risk_level", "LOW"))
        created_str = r.get("created_at", "N/A")
        if "T" in created_str and "Z" in created_str:
            created_str = created_str.split("T")[1].rstrip("Z")

        rows.append([
            r.get("incident_id", ""),
            st_styled,
            risk_styled,
            r.get("namespace", ""),
            r.get("pod", ""),
            str(r.get("risk_score", 0)),
            created_str,
        ])

    print_table(
        columns=["INCIDENT ID", "STATUS", "RISK", "NAMESPACE", "POD", "SCORE", "CREATED"],
        rows=rows,
        column_styles=["cyan", "white", "white", "cyan", "white", "bold white", "dim"],
    )
    console.print()


def _render_incident_detail(inc: dict, as_json: bool = False) -> None:
    if as_json:
        print_json(inc)
        return

    console.print("\n[bold cyan]KubeGuard Incident Detail[/bold cyan]")
    console.print("----------------------------------------", style="dim")

    st = inc.get("status", "active").upper()
    st_styled = f"[bold green]{st}[/bold green]" if st == "RESOLVED" else f"[bold yellow]{st}[/bold yellow]"
    risk_styled = styled_risk(inc.get("risk_level", "LOW"))

    rows = [
        ("Incident ID",  inc.get("incident_id", "")),
        ("Status",       st_styled),
        ("Risk Level",   risk_styled),
        ("Risk Score",   str(inc.get("risk_score", 0))),
        ("Namespace",    inc.get("namespace", "")),
        ("Pod",          inc.get("pod", "")),
        ("Created At",   inc.get("created_at", "")),
        ("Updated At",   inc.get("updated_at", "")),
    ]

    max_key = max(len(r[0]) for r in rows)
    for key, val in rows:
        console.print(f"  [dim]{key:<{max_key}}[/dim] : {val}")

    # Signals
    console.print("\n  [bold white]Signals:[/bold white]")
    signals = inc.get("signals", [])
    if not signals:
        console.print("    [dim]No specific signals recorded[/dim]")
    else:
        for s in signals:
            sev = s.get("severity", "LOW")
            sev_styled = styled_risk(sev)
            tick = get_symbol("✓", "[OK]")
            console.print(f"    [bold green]{tick}[/bold green] [bold]{s.get('signal_name')}[/bold] ({sev_styled}) — {s.get('description')}")

    # Timeline
    console.print("\n  [bold white]Timeline:[/bold white]")
    timeline = inc.get("timeline", [])
    if not timeline:
        console.print("    [dim]No timeline events recorded[/dim]")
    else:
        for t in timeline:
            ts = t.get("timestamp", "").split("T")[-1].rstrip("Z") if "T" in t.get("timestamp", "") else t.get("timestamp", "")
            console.print(f"    [dim]{ts}[/dim]  [cyan]{t.get('event_type')}[/cyan] — {t.get('description')}")

    # Alerts
    alerts = inc.get("alerts", [])
    if alerts:
        console.print("\n  [bold white]Correlated Alerts:[/bold white]")
        for a in alerts:
            res = f"(Resolved {a.get('resolved_at')})" if a.get("resolved_at") else "[bold red]Firing[/bold red]"
            console.print(f"    [yellow]![/yellow] [bold]{a.get('alert_name')}[/bold] ({a.get('severity')}) — {res}")

    # Recommendation
    rec = inc.get("recommendation", "")
    if rec:
        console.print(f"\n  [bold white]Recommendation:[/bold white]\n    {rec}")

    console.print()
