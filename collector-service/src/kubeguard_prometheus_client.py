import sys
from typing import Any, Dict
import requests


class PrometheusClient:
    """Minimal Python client for the Prometheus HTTP API."""

    def __init__(self, base_url: str = "http://localhost:9090") -> None:
        """Initialize the Prometheus client with a base URL.

        Args:
            base_url: The base URL of the Prometheus server.
        """
        self.base_url = base_url.rstrip("/")

    def query(self, promql: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Send a GET request to query Prometheus with a PromQL expression.

        Args:
            promql: The PromQL query string.
            timeout: Request timeout in seconds.

        Returns:
            The 'data' field of the Prometheus response.

        Raises:
            requests.exceptions.RequestException: If the HTTP request fails.
            ValueError: If the API response status is not "success" or data format is invalid.
        """
        url = f"{self.base_url}/api/v1/query"
        params = {"query": promql}

        # Send GET request
        response = requests.get(url, params=params, timeout=timeout)
        
        # Validate HTTP status code
        response.raise_for_status()

        # Parse JSON
        result = response.json()

        # Validate Prometheus response status
        status = result.get("status")
        if status != "success":
            raise ValueError(f"Prometheus query failed with status: {status}. Response: {result}")

        # Extract data field
        data = result.get("data")
        if data is None:
            raise ValueError(f"Prometheus response did not contain 'data' key. Response: {result}")

        return data

    def query_range(
        self,
        promql: str,
        start: str | float | int,
        end: str | float | int,
        step: str | int,
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        """Send a GET request to query Prometheus range API with a PromQL expression.

        Args:
            promql: The PromQL query string.
            start: Start time (Unix timestamp or RFC3339 string).
            end: End time (Unix timestamp or RFC3339 string).
            step: Query resolution step width in duration format or float number of seconds.
            timeout: Request timeout in seconds.

        Returns:
            The 'data' field of the Prometheus response.

        Raises:
            requests.exceptions.RequestException: If the HTTP request fails.
            ValueError: If the API response status is not "success" or data format is invalid.
        """
        url = f"{self.base_url}/api/v1/query_range"
        params = {
            "query": promql,
            "start": start,
            "end": end,
            "step": step
        }

        # Send GET request
        response = requests.get(url, params=params, timeout=timeout)
        
        # Validate HTTP status code
        response.raise_for_status()

        # Parse JSON
        result = response.json()

        # Validate Prometheus response status
        status = result.get("status")
        if status != "success":
            raise ValueError(f"Prometheus range query failed with status: {status}. Response: {result}")

        # Extract data field
        data = result.get("data")
        if data is None:
            raise ValueError(f"Prometheus response did not contain 'data' key. Response: {result}")

        return data



if __name__ == "__main__":
    # Test execution
    client = PrometheusClient()
    query_str = "up"
    print(f"Querying Prometheus with: '{query_str}'...")
    try:
        results = client.query(query_str)
        print("Success! Prometheus returned the following result data:")
        import json
        print(json.dumps(results, indent=2))
    except Exception as e:
        print(f"Error executing query: {e}", file=sys.stderr)
        sys.exit(1)
