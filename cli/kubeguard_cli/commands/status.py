"""kubeguard status - display real cluster state for the KubeGuard installation."""

from __future__ import annotations

import re
import sys
import time
from typing import Optional

import requests
import typer

from kubeguard_cli import DEFAULT_ALERTMANAGER_NS, DEFAULT_ALERTMANAGER_SVC, DEFAULT_NAMESPACE, DEFAULT_RELEASE
from kubeguard_cli.utils import helm, kubectl
from kubeguard_cli.utils.output import console, print_json
from kubeguard_cli.utils.portforward import PortForwardContext


def _deployment_status(dep: Optional[dict]) -> str:
    if not dep:
        return "Not found"
    status = dep.get("status", {})
    ready = status.get("readyReplicas", 0) or 0
    desired = status.get("replicas", 0) or 0
    return f"Ready ({ready}/{desired})" if ready >= 1 else f"Not ready ({ready}/{desired})"


def _pod_phase(pods: list) -> str:
    if not pods:
        return "No pod found"
    phases = [p.get("status", {}).get("phase", "Unknown") for p in pods]
    running = [p for p in phases if p == "Running"]
    return "Running" if running else phases[0]


def status(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", hidden=True),
    release: Optional[str] = typer.Option(None, "--release", hidden=True),
) -> None:
    """Show the current KubeGuard installation status."""
    from kubeguard_cli.main import state
    context = state.context
    ns = namespace or state.namespace
    rel = release or state.release

    # ------------------------------------------------------------------
    # 1. Check installed
    # ------------------------------------------------------------------
    installed = helm.helm_release_exists(rel, ns, context=context)

    if not installed:
        if as_json:
            print_json({"installed": False})
        else:
            console.print(f"\n[yellow]KubeGuard is not installed in namespace '{ns}'.[/yellow]")
            console.print("Run [bold cyan]kubeguard install[/bold cyan] to install.\n")
        sys.exit(0)

    # ------------------------------------------------------------------
    # 2. Gather cluster state
    # ------------------------------------------------------------------
    dep = kubectl.get_deployment(rel, ns, context=context)
    dep_status = _deployment_status(dep)

    pods = kubectl.get_pods(ns, label_selector=f"app.kubernetes.io/name={rel}", context=context)
    if not pods:
        pods = kubectl.get_pods(ns, label_selector=f"app={rel}", context=context)
    pod_phase = _pod_phase(pods)

    svc = kubectl.get_service(rel, ns, context=context)
    svc_status = f"{rel}:8000" if svc else "Not found"

    cm_data = kubectl.get_configmap(f"{rel}-config", ns, context=context) or {}
    interval = cm_data.get("MONITOR_INTERVAL_SECONDS", "30")
    monitored_ns = cm_data.get("MONITOR_NAMESPACES", "demo,kubeguard-test")

    # ------------------------------------------------------------------
    # 3. Check /health, /model, and /metrics via port-forward
    # ------------------------------------------------------------------
    prometheus_status = "Unknown"
    worker_status = "Unknown"
    worker_health_str = "Healthy"
    last_cycle_str = "N/A"
    last_success_str = "N/A"
    feature_records_str = "N/A"
    model_source = "Unknown"
    model_version = "Unknown"

    if svc and pod_phase == "Running":
        try:
            with PortForwardContext(
                target=f"svc/{rel}",
                remote_port=8000,
                namespace=ns,
                context=context,
                timeout=10,
            ) as base_url:
                try:
                    r = requests.get(f"{base_url}/health", timeout=5)
                    if r.ok:
                        h_data = r.json()
                        if h_data.get("status") == "healthy":
                            worker_status = "Running"
                            prometheus_status = "Connected"
                        w_state = h_data.get("worker", "healthy")
                        worker_health_str = w_state.capitalize()
                        model_source = h_data.get("model_source", "Unknown")
                        model_version = str(h_data.get("model_version", "Unknown"))
                    else:
                        worker_status = "Unhealthy"
                        prometheus_status = "Unknown"

                    m_resp = requests.get(f"{base_url}/model", timeout=5)
                    if m_resp.ok:
                        m_data = m_resp.json()
                        model_source = m_data.get("source", model_source)
                        model_version = str(m_data.get("version", model_version))

                    metrics_resp = requests.get(f"{base_url}/metrics", timeout=5)
                    if metrics_resp.ok:
                        metrics_text = metrics_resp.text
                        now = time.time()

                        m_lc = re.search(r"kubeguard_worker_last_cycle_timestamp\s+([\d\.]+)", metrics_text)
                        if m_lc:
                            ts = float(m_lc.group(1))
                            if ts > 0:
                                diff = max(0, int(now - ts))
                                last_cycle_str = f"{diff}s ago"

                        m_ls = re.search(r"kubeguard_worker_last_success_timestamp\s+([\d\.]+)", metrics_text)
                        if m_ls:
                            ts = float(m_ls.group(1))
                            if ts > 0:
                                diff = max(0, int(now - ts))
                                last_success_str = f"{diff}s ago"

                        m_fr = re.search(r"kubeguard_feature_store_records\s+([\d\.]+)", metrics_text)
                        if m_fr:
                            feature_records_str = str(int(float(m_fr.group(1))))
                except Exception:
                    worker_status = "Unreachable"
                    prometheus_status = "Unknown"
        except Exception:
            worker_status = "Port-forward failed"
            prometheus_status = "Unknown"

    # ------------------------------------------------------------------
    # 4. Check Alertmanager service exists
    # ------------------------------------------------------------------
    am_svc = kubectl.get_service(DEFAULT_ALERTMANAGER_SVC, DEFAULT_ALERTMANAGER_NS, context=context)
    alertmanager_status = "Available" if am_svc else "Not found"

    # ------------------------------------------------------------------
    # 5. Output
    # ------------------------------------------------------------------
    data = {
        "installed": True,
        "namespace": ns,
        "release": rel,
        "deployment": dep_status,
        "monitoring": worker_status,
        "worker_health": worker_health_str,
        "last_cycle": last_cycle_str,
        "last_success": last_success_str,
        "prometheus": prometheus_status,
        "alertmanager": alertmanager_status,
        "model_source": model_source,
        "model_version": model_version,
        "feature_records": feature_records_str,
        "service": svc_status,
        "config": {
            "interval": interval,
            "namespaces": monitored_ns,
        },
    }

    if as_json:
        print_json(data)
        return

    console.print("\n[bold cyan]KubeGuard Status[/bold cyan]")
    console.print("----------------------------------------", style="dim")

    def _style(val: str, ok: str, warn: str = "yellow") -> str:
        lower = val.lower()
        if any(k in lower for k in ["ready", "running", "connected", "available", "healthy"]):
            return f"[bold green]{val}[/bold green]"
        if any(k in lower for k in ["not", "fail", "unreachable", "unhealthy", "degraded"]):
            return f"[bold red]{val}[/bold red]"
        return f"[yellow]{val}[/yellow]"

    rows = [
        ("Installation",    "[bold green]Installed[/bold green]"),
        ("Namespace",       ns),
        ("Release",         rel),
        ("Deployment",      _style(dep_status, "ready")),
        ("Monitoring",      _style(worker_status, "running")),
        ("Worker Health",   _style(worker_health_str, "healthy")),
        ("Last Cycle",      last_cycle_str),
        ("Last Success",    last_success_str),
        ("Prometheus",      _style(prometheus_status, "connected")),
        ("Alertmanager",    _style(alertmanager_status, "available")),
        ("Model Source",    f"[bold cyan]{model_source}[/bold cyan]"),
        ("Model Version",   f"v{model_version}"),
        ("Feature Records", feature_records_str),
        ("Service",         svc_status),
    ]

    max_key = max(len(r[0]) for r in rows)
    for key, val in rows:
        console.print(f"  [dim]{key:<{max_key}}[/dim] : {val}")

    console.print(f"\n  [dim]{'Configuration':<{max_key}}[/dim]")
    console.print(f"  [dim]{'  Interval':<{max_key}}[/dim] : {interval}s")
    console.print(f"  [dim]{'  Namespaces':<{max_key}}[/dim] : {monitored_ns}")
    console.print()
