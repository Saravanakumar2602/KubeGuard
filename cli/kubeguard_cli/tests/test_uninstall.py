"""Tests for kubeguard uninstall command (mocked)."""

from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from kubeguard_cli.main import app

runner = CliRunner()


class TestUninstallNotInstalled:
    def test_exits_gracefully_when_not_installed(self):
        with patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=False):
            result = runner.invoke(app, ["uninstall", "--yes"])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower()


class TestUninstallConfirmation:
    def test_yes_flag_skips_confirmation(self):
        m = MagicMock()
        m.returncode = 0

        with (
            patch("kubeguard_cli.utils.helm.helm_release_exists", side_effect=[True, False]),
            patch("kubeguard_cli.utils.helm.helm_uninstall", return_value=m),
        ):
            result = runner.invoke(app, ["uninstall", "--yes"])
        assert result.exit_code == 0
        assert "uninstalled" in result.output.lower()

    def test_without_yes_prompts_user(self):
        m = MagicMock()
        m.returncode = 0

        with (
            patch("kubeguard_cli.utils.helm.helm_release_exists", side_effect=[True, False]),
            patch("kubeguard_cli.utils.helm.helm_uninstall", return_value=m),
        ):
            # Simulate user typing 'y' at the prompt
            result = runner.invoke(app, ["uninstall"], input="y\n")
        assert result.exit_code == 0
        assert "uninstalled" in result.output.lower()

    def test_prompt_cancel_exits_cleanly(self):
        with patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=True):
            result = runner.invoke(app, ["uninstall"], input="n\n")
        assert result.exit_code == 0
        assert "cancel" in result.output.lower()


class TestUninstallFailure:
    def test_shows_error_on_helm_failure(self):
        m = MagicMock()
        m.returncode = 1
        m.stderr = "helm: release not found"

        with (
            patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=True),
            patch("kubeguard_cli.utils.helm.helm_uninstall", return_value=m),
        ):
            result = runner.invoke(app, ["uninstall", "--yes"])
        assert result.exit_code != 0
