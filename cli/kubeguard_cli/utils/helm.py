"""Thin subprocess wrappers around the helm binary."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Internal runner
# ---------------------------------------------------------------------------

def _run(
    args: List[str],
    context: Optional[str] = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run a helm command.

    Args:
        args: helm arguments (without the 'helm' prefix).
        context: optional --kube-context flag value.
        check: raise CalledProcessError on non-zero exit.
        capture: capture stdout/stderr.

    Returns:
        CompletedProcess result.
    """
    cmd = ["helm"]
    if context:
        cmd += ["--kube-context", context]
    cmd += args

    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=check,
    )


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def helm_exists() -> bool:
    """Return True if the helm binary is on PATH."""
    return shutil.which("helm") is not None


def helm_release_exists(
    release: str,
    namespace: str,
    context: Optional[str] = None,
) -> bool:
    """Return True if a Helm release is deployed in the given namespace."""
    result = _run(
        ["list", "-n", namespace, "--filter", release, "-o", "json"],
        context=context,
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        releases = json.loads(result.stdout)
        return any(r.get("name") == release for r in releases)
    except (json.JSONDecodeError, TypeError):
        return False


def get_helm_values(
    release: str,
    namespace: str,
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """Return user-supplied values for a Helm release as a dict."""
    result = _run(
        ["get", "values", release, "-n", namespace, "-o", "json"],
        context=context,
        check=False,
    )
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout) or {}
    except (json.JSONDecodeError, TypeError):
        return {}


def helm_install(
    release: str,
    chart_path: str,
    namespace: str,
    create_namespace: bool = True,
    set_values: Optional[Dict[str, str]] = None,
    context: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Run helm install with the given options."""
    args = [
        "install", release, chart_path,
        "--namespace", namespace,
    ]
    if create_namespace:
        args.append("--create-namespace")
    if set_values:
        for key, value in set_values.items():
            args += ["--set", f"{key}={value}"]
    return _run(args, context=context, check=False)


def helm_uninstall(
    release: str,
    namespace: str,
    context: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Run helm uninstall."""
    return _run(
        ["uninstall", release, "--namespace", namespace],
        context=context,
        check=False,
    )


def run_helm(
    args: List[str],
    context: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Public low-level helm runner."""
    return _run(args, context=context, check=False)
