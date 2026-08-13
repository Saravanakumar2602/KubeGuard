"""Tests for kubeguard version command."""

from typer.testing import CliRunner

from kubeguard_cli import CLI_VERSION, CHART_APP_VERSION
from kubeguard_cli.main import app

runner = CliRunner()


def test_version_output_contains_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert CLI_VERSION in result.output


def test_version_output_contains_app_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert CHART_APP_VERSION in result.output


def test_version_json_flag():
    result = runner.invoke(app, ["version", "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert data["cli_version"] == CLI_VERSION
    assert data["app_version"] == CHART_APP_VERSION


def test_help_shows_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["install", "status", "pods", "alerts", "uninstall", "version"]:
        assert cmd in result.output
