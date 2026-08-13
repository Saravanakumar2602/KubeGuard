"""kubeguard install — install KubeGuard via Helm with pre-flight checks."""

from __future__ import annotations

import os
import sys
from typing import Optional

import typer

from kubeguard_cli import DEFAULT_CHART_PATH, DEFAULT_NAMESPACE, DEFAULT_RELEASE
from kubeguard_cli.utils import helm, kubectl
from kubeguard_cli.utils.output import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from kubeguard_cli.utils.portforward import PortForwardContext


def install(
    namespace: str = typer.Option(
        DEFAULT_NAMESPACE,
        "--namespace", "-n",
        help="Kubernetes namespace to install KubeGuard into.",
    ),
    interval: Optional[int] = typer.Option(
        None,
        "--interval",
        help="Monitoring scan interval in seconds (monitoring.intervalSeconds).",
        min=10,
    ),
    namespaces: Optional[str] = typer.Option(
        None,
        "--namespaces",
        help="Comma-separated namespaces for the monitoring worker (monitoring.namespaces).",
    ),
    chart_path: str = typer.Option(
        DEFAULT_CHART_PATH,
        "--chart-path",
        help="Path to the KubeGuard Helm chart directory.",
    ),
    release: str = typer.Option(
        DEFAULT_RELEASE,
        "--release",
        help="Helm release name.",
        hidden=True,
    ),
) -> None:
    """Install KubeGuard into a Kubernetes cluster using Helm.

    Runs pre-flight checks before installation and waits for the pod to
    become ready.
    """
    # Pull global context from parent state
    from kubeguard_cli.main import state
    context = state.context

    console.print("\n[bold cyan]Installing KubeGuard...[/bold cyan]\n")

    # ------------------------------------------------------------------
    # 1. Pre-flight checks
    # ------------------------------------------------------------------
    if not kubectl.kubectl_exists():
        print_error(
            "kubectl is not installed or not on PATH.",
            hint="Install kubectl: https://kubernetes.io/docs/tasks/tools/",
        )

    if not helm.helm_exists():
        print_error(
            "helm is not installed or not on PATH.",
            hint="Install Helm: https://helm.sh/docs/intro/install/",
        )
    print_success("kubectl and helm found")

    if not kubectl.cluster_reachable(context=context):
        print_error(
            "Kubernetes cluster is unreachable.",
            hint="Run: kubectl cluster-info",
        )
    print_success("Kubernetes connection verified")

    # Resolve chart path relative to CWD
    resolved_chart = os.path.abspath(chart_path)
    if not os.path.isdir(resolved_chart):
        print_error(
            f"Helm chart directory not found: {resolved_chart}",
            hint=f"Run from the KubeGuard repo root, or pass --chart-path <path>",
        )
    print_success(f"Helm chart found: {resolved_chart}")

    # Check if already installed
    if helm.helm_release_exists(release, namespace, context=context):
        print_warning(f"KubeGuard release '{release}' is already installed in namespace '{namespace}'.")
        console.print(
            "\n[dim]Run [bold]kubeguard status[/bold] to inspect the current state."
            "\nTo upgrade, use:[/dim]\n"
            f"  [bold]helm upgrade {release} {chart_path} -n {namespace}[/bold]\n"
        )
        sys.exit(0)

    # ------------------------------------------------------------------
    # 2. Build --set values
    # ------------------------------------------------------------------
    set_values: dict = {}
    if interval is not None:
        set_values["monitoring.intervalSeconds"] = str(interval)
    if namespaces is not None:
        set_values["monitoring.namespaces"] = namespaces

    # ------------------------------------------------------------------
    # 3. Install
    # ------------------------------------------------------------------
    print_info(f"Installing release '{release}' into namespace '{namespace}'...")
    result = helm.helm_install(
        release=release,
        chart_path=resolved_chart,
        namespace=namespace,
        create_namespace=True,
        set_values=set_values or None,
        context=context,
    )
    if result.returncode != 0:
        console.print(f"[red]{result.stderr.strip()}[/red]")
        print_error("Helm install failed. See output above.")
    print_success("KubeGuard installed via Helm")

    # ------------------------------------------------------------------
    # 4. Post-install validation
    # ------------------------------------------------------------------
    print_info("Waiting for deployment to become ready (up to 120s)...")
    ready = kubectl.wait_for_deployment(release, namespace, context=context, timeout=120)
    if not ready:
        print_warning(
            "Deployment did not become ready within 120s. "
            "Check: kubectl get pods -n " + namespace
        )
    else:
        print_success("Deployment ready")

    # Verify /health via port-forward
    try:
        import requests as _req
        with PortForwardContext(
            target=f"svc/{release}",
            remote_port=8000,
            namespace=namespace,
            context=context,
            timeout=15,
        ) as base_url:
            resp = _req.get(f"{base_url}/health", timeout=5)
            if resp.ok and resp.json().get("status") == "healthy":
                print_success("Monitoring worker running")
            else:
                print_warning("Service responded but worker status unclear.")
    except Exception:
        print_warning("Could not verify /health via port-forward (pod may still be initializing).")

    console.print(
        f"\n[bold green]KubeGuard is installed.[/bold green] "
        f"Run [bold cyan]kubeguard status[/bold cyan] to inspect.\n"
    )
