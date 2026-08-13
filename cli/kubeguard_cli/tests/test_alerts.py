"""Tests for kubeguard alerts command (mocked)."""

import json
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from kubeguard_cli.main import app
from kubeguard_cli.commands.alerts import _parse_alerts

runner = CliRunner()

SAMPLE_RAW = [
    {
        "labels": {
            "alertname": "KubeGuardHighRiskPod",
            "exported_namespace": "kubeguard-test",
            "exported_pod": "cpu-stress-xyz",
            "severity": "critical",
        },
        "status": {"state": "active"},
        "startsAt": "2026-08-12T18:00:00Z",
    },
    {
        "labels": {
            "alertname": "KubeGuardMemoryGrowth",
            "exported_namespace": "kubeguard-test",
            "exported_pod": "memory-growth-xyz",
            "severity": "warning",
        },
        "status": {"state": "active"},
        "startsAt": "2026-08-12T18:01:00Z",
    },
    {
        "labels": {
            "alertname": "Watchdog",
            "namespace": "monitoring",
            "severity": "none",
        },
        "status": {"state": "active"},
        "startsAt": "2026-08-12T17:00:00Z",
    },
]


class TestParseAlerts:
    def test_filters_kubeguard_only(self):
        results = _parse_alerts(SAMPLE_RAW)
        names = [r["alert"] for r in results]
        assert "KubeGuardHighRiskPod" in names
        assert "KubeGuardMemoryGrowth" in names
        assert "Watchdog" not in names

    def test_returns_two_kubeguard_alerts(self):
        results = _parse_alerts(SAMPLE_RAW)
        assert len(results) == 2

    def test_fields_populated(self):
        results = _parse_alerts(SAMPLE_RAW)
        by_name = {r["alert"]: r for r in results}
        assert by_name["KubeGuardHighRiskPod"]["namespace"] == "kubeguard-test"
        assert by_name["KubeGuardHighRiskPod"]["pod"] == "cpu-stress-xyz"
        assert by_name["KubeGuardHighRiskPod"]["severity"] == "critical"

    def test_empty_input(self):
        assert _parse_alerts([]) == []

    def test_no_kubeguard_alerts(self):
        assert _parse_alerts([SAMPLE_RAW[2]]) == []


class TestAlertsCommand:
    def _invoke_alerts(self, raw=SAMPLE_RAW, extra_args=None):
        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return raw

        with (
            patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=True),
            patch("kubeguard_cli.utils.kubectl.get_service", return_value={"metadata": {"name": "am"}}),
            patch("kubeguard_cli.utils.portforward.PortForwardContext.__enter__", return_value="http://127.0.0.1:9999"),
            patch("kubeguard_cli.utils.portforward.PortForwardContext.__exit__", return_value=False),
            patch("requests.get", return_value=FakeResp()),
        ):
            args = ["alerts"] + (extra_args or [])
            return runner.invoke(app, args)

    def test_shows_kubeguard_alerts(self):
        result = self._invoke_alerts()
        assert result.exit_code == 0
        assert "KubeGuardHighRiskPod" in result.output
        assert "KubeGuardMemoryGrowth" in result.output

    def test_watchdog_not_shown(self):
        result = self._invoke_alerts()
        assert "Watchdog" not in result.output

    def test_no_alerts_message(self):
        result = self._invoke_alerts(raw=[])
        assert result.exit_code == 0
        assert "no active" in result.output.lower()

    def test_json_output(self):
        result = self._invoke_alerts(extra_args=["--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_not_installed_exits(self):
        with patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=False):
            result = runner.invoke(app, ["alerts"])
        assert result.exit_code != 0
