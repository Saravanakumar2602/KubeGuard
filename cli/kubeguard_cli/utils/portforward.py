"""Transient kubectl port-forward context manager.

Opens a port-forward subprocess, waits until the port is ready, provides
the local URL, then terminates the process on context exit.

Usage::

    with PortForwardContext("svc/kubeguard", 8000, namespace="kubeguard") as url:
        resp = requests.get(f"{url}/health")
"""

from __future__ import annotations

import socket
import subprocess
import time
from typing import Optional


def _find_free_port() -> int:
    """Return an OS-assigned free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 10.0) -> bool:
    """Poll until localhost:port is connectable or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


class PortForwardContext:
    """Context manager that runs kubectl port-forward for the duration of a block.

    Args:
        target: kubectl port-forward target, e.g. ``svc/kubeguard`` or
                ``pod/my-pod-xxx``.
        remote_port: container port to forward.
        namespace: Kubernetes namespace.
        context: kubectl context name (optional).
        local_port: override local port (default: OS-assigned free port).
        timeout: seconds to wait for the port to become ready.
    """

    def __init__(
        self,
        target: str,
        remote_port: int,
        namespace: str,
        context: Optional[str] = None,
        local_port: Optional[int] = None,
        timeout: float = 15.0,
    ) -> None:
        self._target = target
        self._remote_port = remote_port
        self._namespace = namespace
        self._context = context
        self._local_port = local_port or _find_free_port()
        self._timeout = timeout
        self._proc: Optional[subprocess.Popen] = None

    @property
    def url(self) -> str:
        """Return the local base URL for the forwarded port."""
        return f"http://127.0.0.1:{self._local_port}"

    def __enter__(self) -> str:
        cmd = ["kubectl"]
        if self._context:
            cmd += ["--context", self._context]
        cmd += [
            "port-forward",
            self._target,
            f"{self._local_port}:{self._remote_port}",
            "-n", self._namespace,
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if not _wait_for_port(self._local_port, self._timeout):
            self._proc.terminate()
            self._proc = None
            raise RuntimeError(
                f"Port-forward to {self._target}:{self._remote_port} "
                f"did not become ready within {self._timeout}s."
            )

        return self.url

    def __exit__(self, *args) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
