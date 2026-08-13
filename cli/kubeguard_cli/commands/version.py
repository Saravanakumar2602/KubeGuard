"""kubeguard version — display CLI and chart version."""

from __future__ import annotations

import typer
from rich.console import Console

from kubeguard_cli import CLI_VERSION, CHART_APP_VERSION

console = Console()


def version(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Display the KubeGuard CLI and application version."""
    if json:
        import json as _json
        from kubeguard_cli.utils.output import print_json
        print_json({"cli_version": CLI_VERSION, "app_version": CHART_APP_VERSION})
    else:
        console.print(
            f"\n[bold cyan]KubeGuard CLI[/bold cyan]  v[bold]{CLI_VERSION}[/bold]"
        )
        console.print(
            f"[dim]KubeGuard App[/dim]   v[dim]{CHART_APP_VERSION}[/dim]\n"
        )
