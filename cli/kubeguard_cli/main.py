"""KubeGuard CLI — main Typer application."""

from __future__ import annotations

from typing import Optional
import typer

from kubeguard_cli import DEFAULT_NAMESPACE, DEFAULT_RELEASE
from kubeguard_cli.commands import (
    version as version_cmd,
    install as install_cmd,
    status as status_cmd,
    pods as pods_cmd,
    alerts as alerts_cmd,
    incidents as incidents_cmd,
    uninstall as uninstall_cmd,
)


# ---------------------------------------------------------------------------
# Global state passed to sub-commands via Typer callback
# ---------------------------------------------------------------------------
class _State:
    context: Optional[str] = None
    namespace: str = DEFAULT_NAMESPACE
    release: str = DEFAULT_RELEASE


state = _State()

# ---------------------------------------------------------------------------
# Typer application
# ---------------------------------------------------------------------------
app = typer.Typer(
    name="kubeguard",
    help=(
        "[bold cyan]KubeGuard[/bold cyan] — AI-powered Kubernetes health monitoring\n\n"
        "Manage the KubeGuard installation, inspect pod risk scores, and view active alerts."
    ),
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def global_options(
    context: Optional[str] = typer.Option(
        None,
        "--context",
        help="Kubernetes context to use (defaults to current-context).",
        envvar="KUBEGUARD_CONTEXT",
    ),
    namespace: str = typer.Option(
        DEFAULT_NAMESPACE,
        "--namespace", "-n",
        help="KubeGuard Kubernetes namespace.",
        envvar="KUBEGUARD_NAMESPACE",
    ),
    release: str = typer.Option(
        DEFAULT_RELEASE,
        "--release",
        help="Helm release name for KubeGuard.",
        hidden=True,
    ),
) -> None:
    """Global flags that apply to every command."""
    state.context = context
    state.namespace = namespace
    state.release = release


# ---------------------------------------------------------------------------
# Register sub-commands
# ---------------------------------------------------------------------------
app.command("version")(version_cmd.version)
app.command("install")(install_cmd.install)
app.command("status")(status_cmd.status)
app.command("pods")(pods_cmd.pods)
app.command("alerts")(alerts_cmd.alerts)
app.command("incidents")(incidents_cmd.incidents)
app.command("uninstall")(uninstall_cmd.uninstall)



# ---------------------------------------------------------------------------
# Entry-point (console_scripts)
# ---------------------------------------------------------------------------
def app_entry() -> None:
    """Console script entry point registered in pyproject.toml."""
    app()


if __name__ == "__main__":
    app_entry()
