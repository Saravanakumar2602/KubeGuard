"""Tests for kubeguard status command (mocked)."""

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from kubeguard_cli.main import app

runner = CliRunner()

_DEP_READY = {
    "status": {"readyReplicas": 1, "replicas": 1}
}
_DEP_NOT_READY = {
    "status": {"readyReplicas": 0, "replicas": 1}
}


class TestStatusNotInstalled:
    def test_shows_not_installed_message(self):
        with patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=False):
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower()


class TestStatusInstalled:
    def _base_patches(self):
        return {
            "kubeguard_cli.utils.helm.helm_release_exists": True,
            "kubeguard_cli.utils.kubectl.get_deployment": _DEP_READY,
            "kubeguard_cli.utils.kubectl.get_pods": [
                {"status": {"phase": "Running"}}
            ],
            "kubeguard_cli.utils.kubectl.get_service": {"metadata": {"name": "kubeguard"}},
            "kubeguard_cli.utils.kubectl.get_configmap": {
                "MONITOR_INTERVAL_SECONDS": "60",
                "MONITOR_NAMESPACES": "demo,kubeguard-test",
            },
        }

    def test_shows_installed_status(self):
        patches = self._base_patches()
        with (
            patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=patches["kubeguard_cli.utils.helm.helm_release_exists"]),
            patch("kubeguard_cli.utils.kubectl.get_deployment", return_value=patches["kubeguard_cli.utils.kubectl.get_deployment"]),
            patch("kubeguard_cli.utils.kubectl.get_pods", return_value=patches["kubeguard_cli.utils.kubectl.get_pods"]),
            patch("kubeguard_cli.utils.kubectl.get_service", return_value=patches["kubeguard_cli.utils.kubectl.get_service"]),
            patch("kubeguard_cli.utils.kubectl.get_configmap", return_value=patches["kubeguard_cli.utils.kubectl.get_configmap"]),
            patch("kubeguard_cli.utils.portforward.PortForwardContext.__enter__", side_effect=RuntimeError("skip")),
            patch("kubeguard_cli.utils.portforward.PortForwardContext.__exit__", return_value=False),
        ):
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Installed" in result.output
        assert "kubeguard" in result.output.lower()

    def test_json_output_contains_installed_key(self):
        patches = self._base_patches()
        with (
            patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=True),
            patch("kubeguard_cli.utils.kubectl.get_deployment", return_value=_DEP_READY),
            patch("kubeguard_cli.utils.kubectl.get_pods", return_value=[{"status": {"phase": "Running"}}]),
            patch("kubeguard_cli.utils.kubectl.get_service", return_value={"metadata": {"name": "kubeguard"}}),
            patch("kubeguard_cli.utils.kubectl.get_configmap", return_value={"MONITOR_INTERVAL_SECONDS": "60", "MONITOR_NAMESPACES": "demo"}),
            patch("kubeguard_cli.utils.portforward.PortForwardContext.__enter__", side_effect=RuntimeError("skip")),
            patch("kubeguard_cli.utils.portforward.PortForwardContext.__exit__", return_value=False),
        ):
            result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["installed"] is True
        assert "deployment" in data
        assert "config" in data
