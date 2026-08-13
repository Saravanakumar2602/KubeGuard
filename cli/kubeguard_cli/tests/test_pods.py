"""Tests for kubeguard pods command (mocked)."""

import json
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from kubeguard_cli.main import app
from kubeguard_cli.commands.pods import _parse_metrics

runner = CliRunner()

# ---------------------------------------------------------------------------
# Parser unit tests (no subprocess / CLI involved)
# ---------------------------------------------------------------------------

SAMPLE_METRICS = """\
# HELP kubeguard_pod_risk_score Operational risk score of the pod (0-100)
# TYPE kubeguard_pod_risk_score gauge
kubeguard_pod_risk_score{container="prediction-service",endpoint="http",exported_namespace="demo",exported_pod="demo-nginx-abc",instance="10.0.0.1:8000",job="kubeguard",namespace="kubeguard",pod="kubeguard-xyz",service="kubeguard"} 40
kubeguard_pod_risk_score{container="prediction-service",endpoint="http",exported_namespace="kubeguard-test",exported_pod="cpu-stress-xyz",instance="10.0.0.1:8000",job="kubeguard",namespace="kubeguard",pod="kubeguard-xyz",service="kubeguard"} 85
# HELP kubeguard_pod_risk_level One-hot encoded risk level of the pod
# TYPE kubeguard_pod_risk_level gauge
kubeguard_pod_risk_level{container="prediction-service",endpoint="http",exported_namespace="demo",exported_pod="demo-nginx-abc",instance="10.0.0.1:8000",job="kubeguard",level="LOW",namespace="kubeguard",pod="kubeguard-xyz",service="kubeguard"} 1
kubeguard_pod_risk_level{container="prediction-service",endpoint="http",exported_namespace="demo",exported_pod="demo-nginx-abc",instance="10.0.0.1:8000",job="kubeguard",level="MEDIUM",namespace="kubeguard",pod="kubeguard-xyz",service="kubeguard"} 0
kubeguard_pod_risk_level{container="prediction-service",endpoint="http",exported_namespace="demo",exported_pod="demo-nginx-abc",instance="10.0.0.1:8000",job="kubeguard",level="HIGH",namespace="kubeguard",pod="kubeguard-xyz",service="kubeguard"} 0
kubeguard_pod_risk_level{container="prediction-service",endpoint="http",exported_namespace="kubeguard-test",exported_pod="cpu-stress-xyz",instance="10.0.0.1:8000",job="kubeguard",level="LOW",namespace="kubeguard",pod="kubeguard-xyz",service="kubeguard"} 0
kubeguard_pod_risk_level{container="prediction-service",endpoint="http",exported_namespace="kubeguard-test",exported_pod="cpu-stress-xyz",instance="10.0.0.1:8000",job="kubeguard",level="MEDIUM",namespace="kubeguard",pod="kubeguard-xyz",service="kubeguard"} 0
kubeguard_pod_risk_level{container="prediction-service",endpoint="http",exported_namespace="kubeguard-test",exported_pod="cpu-stress-xyz",instance="10.0.0.1:8000",job="kubeguard",level="HIGH",namespace="kubeguard",pod="kubeguard-xyz",service="kubeguard"} 1
"""


# Direct label form — as seen when port-forwarding to /metrics directly
SAMPLE_METRICS_DIRECT = """\
# HELP kubeguard_pod_risk_score Operational risk score of the pod (0-100)
# TYPE kubeguard_pod_risk_score gauge
kubeguard_pod_risk_score{namespace="demo",pod="demo-nginx-abc"} 40
kubeguard_pod_risk_score{namespace="kubeguard-test",pod="cpu-stress-xyz"} 85
# HELP kubeguard_pod_risk_level One-hot encoded risk level of the pod
# TYPE kubeguard_pod_risk_level gauge
kubeguard_pod_risk_level{namespace="demo",pod="demo-nginx-abc",level="LOW"} 1
kubeguard_pod_risk_level{namespace="demo",pod="demo-nginx-abc",level="MEDIUM"} 0
kubeguard_pod_risk_level{namespace="demo",pod="demo-nginx-abc",level="HIGH"} 0
kubeguard_pod_risk_level{namespace="kubeguard-test",pod="cpu-stress-xyz",level="LOW"} 0
kubeguard_pod_risk_level{namespace="kubeguard-test",pod="cpu-stress-xyz",level="MEDIUM"} 0
kubeguard_pod_risk_level{namespace="kubeguard-test",pod="cpu-stress-xyz",level="HIGH"} 1
"""


class TestParseMetrics:
    def test_parses_two_pods(self):
        records = _parse_metrics(SAMPLE_METRICS)
        assert len(records) == 2

    def test_score_parsed_correctly(self):
        records = _parse_metrics(SAMPLE_METRICS)
        by_pod = {r["pod"]: r for r in records}
        assert by_pod["demo-nginx-abc"]["risk_score"] == 40
        assert by_pod["cpu-stress-xyz"]["risk_score"] == 85

    def test_risk_level_parsed_correctly(self):
        records = _parse_metrics(SAMPLE_METRICS)
        by_pod = {r["pod"]: r for r in records}
        assert by_pod["demo-nginx-abc"]["risk_level"] == "LOW"
        assert by_pod["cpu-stress-xyz"]["risk_level"] == "HIGH"

    def test_sorted_by_score_descending(self):
        records = _parse_metrics(SAMPLE_METRICS)
        scores = [r["risk_score"] for r in records]
        assert scores == sorted(scores, reverse=True)

    def test_empty_metrics(self):
        records = _parse_metrics("# no data\n")
        assert records == []

    def test_direct_labels_namespace_pod_form(self):
        """Parser must work with namespace/pod labels (direct /metrics) as well."""
        records = _parse_metrics(SAMPLE_METRICS_DIRECT)
        assert len(records) == 2
        by_pod = {r["pod"]: r for r in records}
        assert by_pod["demo-nginx-abc"]["risk_score"] == 40
        assert by_pod["demo-nginx-abc"]["risk_level"] == "LOW"
        assert by_pod["cpu-stress-xyz"]["risk_score"] == 85
        assert by_pod["cpu-stress-xyz"]["risk_level"] == "HIGH"


# ---------------------------------------------------------------------------
# CLI integration tests (mocked port-forward + requests)
# ---------------------------------------------------------------------------

class TestPodsCommand:
    def _invoke_pods(self, extra_args=None, metrics_text=SAMPLE_METRICS):
        class FakeResp:
            text = metrics_text
            def raise_for_status(self): pass

        with (
            patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=True),
            patch("kubeguard_cli.utils.portforward.PortForwardContext.__enter__", return_value="http://127.0.0.1:9999"),
            patch("kubeguard_cli.utils.portforward.PortForwardContext.__exit__", return_value=False),
            patch("requests.get", return_value=FakeResp()),
        ):
            args = ["pods"] + (extra_args or [])
            return runner.invoke(app, args)

    def test_shows_both_pods(self):
        result = self._invoke_pods()
        assert result.exit_code == 0
        assert "demo-nginx-abc" in result.output
        assert "cpu-stress-xyz" in result.output

    def test_namespace_filter(self):
        result = self._invoke_pods(["--namespace", "demo"])
        assert result.exit_code == 0
        assert "demo-nginx-abc" in result.output
        assert "cpu-stress-xyz" not in result.output

    def test_risk_filter_high(self):
        result = self._invoke_pods(["--risk", "high"])
        assert result.exit_code == 0
        assert "cpu-stress-xyz" in result.output
        assert "demo-nginx-abc" not in result.output

    def test_json_output(self):
        result = self._invoke_pods(["--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_no_results_message(self):
        result = self._invoke_pods(["--risk", "critical"])
        assert result.exit_code == 0

    def test_not_installed_exits(self):
        with patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=False):
            result = runner.invoke(app, ["pods"])
        assert result.exit_code != 0
