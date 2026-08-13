"""Thin subprocess wrappers around the kubectl binary."""

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
    """Run a kubectl command.

    Args:
        args: kubectl arguments (without the 'kubectl' prefix).
        context: optional --context flag value.
        check: raise CalledProcessError on non-zero exit.
        capture: capture stdout/stderr.

    Returns:
        CompletedProcess result.
    """
    cmd = ["kubectl"]
    if context:
        cmd += ["--context", context]
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

def kubectl_exists() -> bool:
    """Return True if kubectl binary is on PATH."""
    return shutil.which("kubectl") is not None


def cluster_reachable(context: Optional[str] = None) -> bool:
    """Return True if the Kubernetes API server responds."""
    result = _run(["cluster-info"], context=context, check=False)
    return result.returncode == 0


def get_deployment(
    name: str,
    namespace: str,
    context: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return JSON of a deployment or None if not found."""
    result = _run(
        ["get", "deployment", name, "-n", namespace, "-o", "json"],
        context=context,
        check=False,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def get_pods(
    namespace: str,
    label_selector: Optional[str] = None,
    context: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return a list of pod JSON objects."""
    args = ["get", "pods", "-n", namespace, "-o", "json"]
    if label_selector:
        args += ["-l", label_selector]
    result = _run(args, context=context, check=False)
    if result.returncode != 0:
        return []
    return json.loads(result.stdout).get("items", [])


def get_service(
    name: str,
    namespace: str,
    context: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return JSON of a service or None if not found."""
    result = _run(
        ["get", "service", name, "-n", namespace, "-o", "json"],
        context=context,
        check=False,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def get_configmap(
    name: str,
    namespace: str,
    context: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return the data dict of a ConfigMap or None."""
    result = _run(
        ["get", "configmap", name, "-n", namespace, "-o", "json"],
        context=context,
        check=False,
    )
    if result.returncode != 0:
        return None
    raw = json.loads(result.stdout)
    return raw.get("data", {})


def deployment_ready(
    name: str,
    namespace: str,
    context: Optional[str] = None,
) -> bool:
    """Return True if the deployment has at least 1 ready replica."""
    dep = get_deployment(name, namespace, context)
    if not dep:
        return False
    status = dep.get("status", {})
    ready = status.get("readyReplicas", 0)
    return ready >= 1


def wait_for_deployment(
    name: str,
    namespace: str,
    context: Optional[str] = None,
    timeout: int = 120,
) -> bool:
    """Block until deployment is available or timeout (seconds)."""
    args = [
        "rollout", "status", "deployment", name,
        "-n", namespace,
        f"--timeout={timeout}s",
    ]
    result = _run(args, context=context, check=False)
    return result.returncode == 0


def run_kubectl(
    args: List[str],
    context: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Public low-level kubectl runner for commands not covered above."""
    return _run(args, context=context, check=False)
