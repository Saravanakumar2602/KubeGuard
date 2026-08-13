"""kubeguard uninstall — remove the KubeGuard Helm release."""

from __future__ import annotations

import sys

import typer

from kubeguard_cli import DEFAULT_NAMESPACE, DEFAULT_RELEASE
from kubeguard_cli.utils import helm
from kubeguard_cli.utils.output import console, print_error, print_success, print_warning


def uninstall(
    yes: bool = typer.Option(
        False,
        "--yes", "-y",
        help="Skip confirmation prompt.",
    ),
    namespace: str = typer.Option(
        DEFAULT_NAMESPACE,
        "--namespace", "-n",
        help="Namespace where KubeGuard is installed.",
    ),
    release: str = typer.Option(
        DEFAULT_RELEASE,
        "--release",
        help="Helm release name.",
        hidden=True,
    ),
) -> None:
    """Remove the KubeGuard Helm release.

    Only the KubeGuard Helm release is removed. Prometheus, Grafana,
    Alertmanager, and workload namespaces are NOT affected.
    """
    from kubeguard_cli.main import state
    context = state.context
    ns = namespace or state.namespace
    rel = release or state.release

    # Check installed
    if not helm.helm_release_exists(rel, ns, context=context):
        console.print(
            f"\n[yellow]KubeGuard release '{rel}' is not installed in namespace '{ns}'.[/yellow]\n"
        )
        sys.exit(0)

    # Confirmation
    if not yes:
        console.print(
            f"\n[bold yellow]This will remove the KubeGuard Helm release '[/bold yellow]"
            f"[bold]{rel}[/bold][bold yellow]' from namespace '[/bold yellow]"
            f"[bold]{ns}[/bold][bold yellow]'.[/bold yellow]\n"
        )
        console.print("[dim]Prometheus, Grafana, Alertmanager, and workload pods are NOT affected.[/dim]\n")
        confirmed = typer.confirm("Proceed with uninstall?", default=False)
        if not confirmed:
            console.print("\n[dim]Uninstall cancelled.[/dim]\n")
            sys.exit(0)

    # Uninstall
    result = helm.helm_uninstall(rel, ns, context=context)
    if result.returncode != 0:
        console.print(f"[red]{result.stderr.strip()}[/red]")
        print_error("Helm uninstall failed.")

    # Verify removed
    if helm.helm_release_exists(rel, ns, context=context):
        print_warning(f"Release '{rel}' still appears in helm list. It may take a moment to fully terminate.")
    else:
        print_success(f"KubeGuard release '{rel}' uninstalled from namespace '{ns}'.")

    console.print(
        "\n[dim]Run [bold]kubeguard install[/bold] to reinstall.[/dim]\n"
    )
