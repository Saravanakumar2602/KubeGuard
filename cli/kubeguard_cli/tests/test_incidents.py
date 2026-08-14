"""Unit tests for CLI kubeguard incidents command."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from kubeguard_cli.main import app

runner = CliRunner()


@pytest.fixture
def mock_not_installed():
    with patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=False):
        yield


@pytest.fixture
def mock_installed():
    with patch("kubeguard_cli.utils.helm.helm_release_exists", return_value=True):
        yield


@pytest.fixture
def mock_portforward():
    with patch("kubeguard_cli.commands.incidents.PortForwardContext") as mock_pf:
        ctx_instance = MagicMock()
        ctx_instance.__enter__.return_value = "http://localhost:8000"
        mock_pf.return_value = ctx_instance
        yield mock_pf


class TestIncidentsCommandNotInstalled:

    def test_exits_when_not_installed(self, mock_not_installed):
        result = runner.invoke(app, ["incidents"])
        assert result.exit_code == 1
        assert "not installed" in result.output.lower()


class TestIncidentsCommandList:

    @patch("requests.get")
    def test_shows_incidents_table(self, mock_get, mock_installed, mock_portforward):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = [
            {
                "incident_id": "demo/pod-1/1000",
                "namespace": "demo",
                "pod": "pod-1",
                "status": "active",
                "risk_level": "HIGH",
                "risk_score": 85,
                "created_at": "2026-08-13T10:00:00Z",
                "updated_at": "2026-08-13T10:00:00Z",
                "signals": [],
                "timeline": [],
                "alerts": [],
                "recommendation": "Investigate memory growth.",
            }
        ]
        mock_get.return_value = mock_resp

        result = runner.invoke(app, ["incidents"])
        assert result.exit_code == 0
        assert "KubeGuard Incidents" in result.output
        assert "pod-1" in result.output
        assert "HIGH" in result.output

    @patch("requests.get")
    def test_json_output(self, mock_get, mock_installed, mock_portforward):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = [
            {
                "incident_id": "demo/pod-1/1000",
                "namespace": "demo",
                "pod": "pod-1",
                "status": "active",
                "risk_level": "HIGH",
                "risk_score": 85,
            }
        ]
        mock_get.return_value = mock_resp

        result = runner.invoke(app, ["incidents", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 1
        assert parsed[0]["incident_id"] == "demo/pod-1/1000"


class TestIncidentsCommandDetail:

    @patch("requests.get")
    def test_shows_incident_detail(self, mock_get, mock_installed, mock_portforward):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "incident_id": "demo/pod-1/1000",
            "namespace": "demo",
            "pod": "pod-1",
            "status": "active",
            "risk_level": "HIGH",
            "risk_score": 85,
            "created_at": "2026-08-13T10:00:00Z",
            "updated_at": "2026-08-13T10:00:00Z",
            "signals": [
                {"signal_name": "memory_growth", "severity": "HIGH", "value": "5000 B/s", "description": "Memory growth detected.", "detected_at": "2026-08-13T10:00:00Z"}
            ],
            "timeline": [
                {"timestamp": "2026-08-13T10:00:00Z", "event_type": "incident_created", "description": "Incident created", "severity": "high"}
            ],
            "alerts": [],
            "recommendation": "Investigate memory growth.",
        }
        mock_get.return_value = mock_resp

        result = runner.invoke(app, ["incidents", "--id", "demo/pod-1/1000"])
        assert result.exit_code == 0
        assert "KubeGuard Incident Detail" in result.output
        assert "demo/pod-1/1000" in result.output
        assert "memory_growth" in result.output
        assert "Investigate memory growth." in result.output
