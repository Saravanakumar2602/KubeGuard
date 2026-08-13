"""Tests for kubectl and helm utility wrappers."""

import subprocess
from unittest.mock import MagicMock, patch

from kubeguard_cli.utils import kubectl, helm


# ---------------------------------------------------------------------------
# kubectl helpers
# ---------------------------------------------------------------------------

class TestKubectlExists:
    def test_returns_true_when_on_path(self):
        with patch("shutil.which", return_value="/usr/bin/kubectl"):
            assert kubectl.kubectl_exists() is True

    def test_returns_false_when_not_on_path(self):
        with patch("shutil.which", return_value=None):
            assert kubectl.kubectl_exists() is False


class TestClusterReachable:
    def test_returns_true_on_exit_zero(self):
        mock = MagicMock()
        mock.returncode = 0
        with patch("subprocess.run", return_value=mock):
            assert kubectl.cluster_reachable() is True

    def test_returns_false_on_nonzero(self):
        mock = MagicMock()
        mock.returncode = 1
        with patch("subprocess.run", return_value=mock):
            assert kubectl.cluster_reachable() is False


class TestGetDeployment:
    def test_returns_dict_on_success(self):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = '{"status": {"readyReplicas": 1, "replicas": 1}}'
        with patch("subprocess.run", return_value=mock):
            result = kubectl.get_deployment("kubeguard", "kubeguard")
        assert result is not None
        assert result["status"]["readyReplicas"] == 1

    def test_returns_none_on_failure(self):
        mock = MagicMock()
        mock.returncode = 1
        with patch("subprocess.run", return_value=mock):
            result = kubectl.get_deployment("kubeguard", "kubeguard")
        assert result is None


class TestDeploymentReady:
    def test_ready_when_replicas_gte_1(self):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = '{"status": {"readyReplicas": 1}}'
        with patch("subprocess.run", return_value=mock):
            assert kubectl.deployment_ready("kubeguard", "kubeguard") is True

    def test_not_ready_when_no_replicas(self):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = '{"status": {"readyReplicas": 0}}'
        with patch("subprocess.run", return_value=mock):
            assert kubectl.deployment_ready("kubeguard", "kubeguard") is False


class TestGetConfigmap:
    def test_returns_data_dict(self):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = '{"data": {"MONITOR_INTERVAL_SECONDS": "60", "MONITOR_NAMESPACES": "demo"}}'
        with patch("subprocess.run", return_value=mock):
            result = kubectl.get_configmap("kubeguard-config", "kubeguard")
        assert result["MONITOR_INTERVAL_SECONDS"] == "60"

    def test_returns_none_on_failure(self):
        mock = MagicMock()
        mock.returncode = 1
        with patch("subprocess.run", return_value=mock):
            result = kubectl.get_configmap("kubeguard-config", "kubeguard")
        assert result is None


# ---------------------------------------------------------------------------
# helm helpers
# ---------------------------------------------------------------------------

class TestHelmExists:
    def test_returns_true_when_on_path(self):
        with patch("shutil.which", return_value="/usr/local/bin/helm"):
            assert helm.helm_exists() is True

    def test_returns_false_when_not_on_path(self):
        with patch("shutil.which", return_value=None):
            assert helm.helm_exists() is False


class TestHelmReleaseExists:
    def test_returns_true_when_release_present(self):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = '[{"name": "kubeguard", "status": "deployed"}]'
        with patch("subprocess.run", return_value=mock):
            assert helm.helm_release_exists("kubeguard", "kubeguard") is True

    def test_returns_false_when_not_present(self):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = "[]"
        with patch("subprocess.run", return_value=mock):
            assert helm.helm_release_exists("kubeguard", "kubeguard") is False

    def test_returns_false_on_error(self):
        mock = MagicMock()
        mock.returncode = 1
        with patch("subprocess.run", return_value=mock):
            assert helm.helm_release_exists("kubeguard", "kubeguard") is False


class TestHelmInstallCommand:
    def test_builds_correct_args_with_set_values(self):
        captured = []

        def fake_run(cmd, **kwargs):
            captured.extend(cmd)
            m = MagicMock()
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=fake_run):
            helm.helm_install(
                "kubeguard",
                "helm/kubeguard",
                "kubeguard",
                set_values={"monitoring.intervalSeconds": "45"},
            )

        assert "install" in captured
        assert "kubeguard" in captured
        assert "--set" in captured
        assert "monitoring.intervalSeconds=45" in captured


class TestHelmUninstallCommand:
    def test_builds_correct_args(self):
        captured = []

        def fake_run(cmd, **kwargs):
            captured.extend(cmd)
            m = MagicMock()
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=fake_run):
            helm.helm_uninstall("kubeguard", "kubeguard")

        assert "uninstall" in captured
        assert "kubeguard" in captured
        assert "--namespace" in captured
