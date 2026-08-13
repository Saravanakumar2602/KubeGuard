"""Tests for kubeguard install command (mocked subprocess)."""

import os
from unittest.mock import MagicMock, patch, call

import pytest
from typer.testing import CliRunner

from kubeguard_cli.main import app

runner = CliRunner()


def _mock_run_ok():
    m = MagicMock()
    m.returncode = 0
    m.stdout = ""
    m.stderr = ""
    return m


def _mock_run_fail(stderr="error"):
    m = MagicMock()
    m.returncode = 1
    m.stdout = ""
    m.stderr = stderr
    return m


class TestInstallPreflightChecks:
    def test_fails_when_kubectl_missing(self):
        with patch("kubeguard_cli.utils.kubectl.kubectl_exists", return_value=False):
            result = runner.invoke(app, ["install"])
        assert result.exit_code != 0

    def test_fails_when_helm_missing(self):
        with (
            patch("kubeguard_cli.utils.kubectl.kubectl_exists", return_value=True),
            patch("kubeguard_cli.utils.helm.helm_exists", return_value=False),
        ):
            result = runner.invoke(app, ["install"])
        assert result.exit_code != 0

    def test_fails_when_cluster_unreachable(self):
        with (
            patch("kubeguard_cli.utils.kubectl.kubectl_exists", return_value=True),
            patch("kubeguard_cli.utils.helm.helm_exists", return_value=True),
            patch("kubeguard_cli.utils.kubectl.cluster_reachable", return_value=False),
        ):
            result = runner.invoke(app, ["install"])
        assert result.exit_code != 0

    def test_fails_when_chart_path_missing(self, tmp_path):
        with (
            patch("kubeguard_cli.utils.kubectl.kubectl_exists", return_value=True),
            patch("kubeguard_cli.utils.helm.helm_exists", return_value=True),
            patch("kubeguard_cli.utils.kubectl.cluster_reachable", return_value=True),
        ):
            result = runner.invoke(app, ["install", "--chart-path", "/nonexistent/path"])
        assert result.exit_code != 0

    def test_warns_if_already_installed(self, tmp_path):
        (tmp_path / "Chart.yaml").write_text("name: kubeguard")
        with (
            patch("kubeguard_cli.utils.kubectl.kubectl_exists", return_value=True),
            patch("kubeguard_cli.utils.helm.helm_exists", return_value=True),
            patch("kubeguard_cli.utils.kubectl.cluster_reachable", return_value=True),
            patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=True),
        ):
            result = runner.invoke(app, ["install", "--chart-path", str(tmp_path)])
        assert result.exit_code == 0
        assert "already installed" in result.output.lower()


class TestInstallSetValues:
    def test_passes_interval_to_helm(self, tmp_path):
        (tmp_path / "Chart.yaml").write_text("name: kubeguard")
        captured_set_values = {}

        def fake_install(release, chart_path, namespace, create_namespace, set_values, context):
            captured_set_values.update(set_values or {})
            m = MagicMock()
            m.returncode = 0
            m.stderr = ""
            return m

        with (
            patch("kubeguard_cli.utils.kubectl.kubectl_exists", return_value=True),
            patch("kubeguard_cli.utils.helm.helm_exists", return_value=True),
            patch("kubeguard_cli.utils.kubectl.cluster_reachable", return_value=True),
            patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=False),
            patch("kubeguard_cli.utils.helm.helm_install", side_effect=fake_install),
            patch("kubeguard_cli.utils.kubectl.wait_for_deployment", return_value=False),
            patch("kubeguard_cli.utils.portforward.PortForwardContext.__enter__", side_effect=RuntimeError("skip")),
            patch("kubeguard_cli.utils.portforward.PortForwardContext.__exit__", return_value=False),
        ):
            runner.invoke(app, ["install", "--chart-path", str(tmp_path), "--interval", "45"])

        assert captured_set_values.get("monitoring.intervalSeconds") == "45"

    def test_passes_namespaces_to_helm(self, tmp_path):
        (tmp_path / "Chart.yaml").write_text("name: kubeguard")
        captured_set_values = {}

        def fake_install(release, chart_path, namespace, create_namespace, set_values, context):
            captured_set_values.update(set_values or {})
            m = MagicMock()
            m.returncode = 0
            m.stderr = ""
            return m

        with (
            patch("kubeguard_cli.utils.kubectl.kubectl_exists", return_value=True),
            patch("kubeguard_cli.utils.helm.helm_exists", return_value=True),
            patch("kubeguard_cli.utils.kubectl.cluster_reachable", return_value=True),
            patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=False),
            patch("kubeguard_cli.utils.helm.helm_install", side_effect=fake_install),
            patch("kubeguard_cli.utils.kubectl.wait_for_deployment", return_value=False),
            patch("kubeguard_cli.utils.portforward.PortForwardContext.__enter__", side_effect=RuntimeError("skip")),
            patch("kubeguard_cli.utils.portforward.PortForwardContext.__exit__", return_value=False),
        ):
            runner.invoke(app, ["install", "--chart-path", str(tmp_path), "--namespaces", "demo,test"])

        assert captured_set_values.get("monitoring.namespaces") == "demo,test"
