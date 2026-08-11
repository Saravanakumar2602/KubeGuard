import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import List, Dict, Tuple

# Resolve path to import from collector-service
current_dir = os.path.dirname(os.path.abspath(__file__))
collector_src = os.path.abspath(os.path.join(current_dir, "../../collector-service/src"))
if collector_src not in sys.path:
    sys.path.append(collector_src)

from prometheus_client import PrometheusClient
from collector import Collector


@dataclass
class MetricSample:
    """Represents a single metric data point with timestamp and value."""
    timestamp: float
    value: float


@dataclass
class PodMetricHistory:
    """Represents historical metric samples for a specific pod."""
    pod: str
    metric: str
    samples: List[MetricSample]
    namespace: str


@dataclass
class PodFeatures:
    """Represents calculated features for a pod, suitable for ML input."""
    pod: str
    namespace: str
    cpu_current: float | None
    cpu_average: float | None
    cpu_max: float | None
    cpu_min: float | None
    cpu_trend: float | None  # CPU units per second
    memory_current: float | None
    memory_average: float | None
    memory_max: float | None
    memory_min: float | None
    memory_trend: float | None  # Bytes per second
    restart_count: int


class FeatureService:
    """Service to retrieve historical time-series data and calculate numerical features."""

    def __init__(self, prometheus_client: PrometheusClient) -> None:
        """Initialize FeatureService with a PrometheusClient instance.

        Args:
            prometheus_client: An instance of PrometheusClient.
        """
        self.client = prometheus_client

    def _parse_range_response(self, data: dict, metric_name: str, fallback_namespace: str) -> List[PodMetricHistory]:
        """Parse Prometheus matrix (range query) response into structured Python objects."""
        histories = []
        for item in data.get("result", []):
            metric = item.get("metric", {})
            pod_name = metric.get("pod")
            namespace = metric.get("namespace", fallback_namespace)
            if not pod_name:
                continue

            samples = []
            for val_pair in item.get("values", []):
                if len(val_pair) == 2:
                    try:
                        ts = float(val_pair[0])
                        val = float(val_pair[1])
                        samples.append(MetricSample(timestamp=ts, value=val))
                    except (ValueError, TypeError):
                        continue
            
            histories.append(
                PodMetricHistory(
                    pod=pod_name,
                    metric=metric_name,
                    samples=samples,
                    namespace=namespace
                )
            )
        return histories

    def get_cpu_history(
        self,
        namespace: str,
        start: float,
        end: float,
        step: int = 60
    ) -> List[PodMetricHistory]:
        """Retrieve CPU usage history for pods in the namespace.

        Args:
            namespace: The Kubernetes namespace.
            start: Start time (Unix timestamp).
            end: End time (Unix timestamp).
            step: Step interval in seconds.

        Returns:
            A list of PodMetricHistory objects.
        """
        query = (
            f'sum by (pod, namespace) ('
            f'  rate(container_cpu_usage_seconds_total{{'
            f'    namespace="{namespace}",'
            f'    container!="",'
            f'    container!="POD"'
            f'  }}[5m])'
            f')'
        )
        data = self.client.query_range(promql=query, start=start, end=end, step=step)
        return self._parse_range_response(data, "cpu", namespace)

    def get_memory_history(
        self,
        namespace: str,
        start: float,
        end: float,
        step: int = 60
    ) -> List[PodMetricHistory]:
        """Retrieve Memory usage history for pods in the namespace.

        Args:
            namespace: The Kubernetes namespace.
            start: Start time (Unix timestamp).
            end: End time (Unix timestamp).
            step: Step interval in seconds.

        Returns:
            A list of PodMetricHistory objects.
        """
        query = (
            f'sum by (pod, namespace) ('
            f'  container_memory_working_set_bytes{{'
            f'    namespace="{namespace}",'
            f'    container!="",'
            f'    container!="POD"'
            f'  }}'
            f')'
        )
        data = self.client.query_range(promql=query, start=start, end=end, step=step)
        return self._parse_range_response(data, "memory", namespace)

    def _calculate_trend(self, samples: List[MetricSample]) -> float | None:
        """Calculate linear regression slope using actual timestamps.

        Normalized so x starts at 0 to prevent numerical precision issues.
        Returns:
            Slope representing rate of change per second (e.g. bytes/sec or cpu/sec).
            0.0 if there is only 1 sample.
            None if no samples.
        """
        if not samples:
            return None
        if len(samples) == 1:
            return 0.0

        # x: elapsed seconds since the first sample
        first_ts = samples[0].timestamp
        x = [s.timestamp - first_ts for s in samples]
        y = [s.value for s in samples]

        n = len(samples)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xx = sum(val * val for val in x)
        sum_xy = sum(x[i] * y[i] for i in range(n))

        # Check for division by zero (e.g. all timestamps identical)
        denominator = n * sum_xx - sum_x * sum_x
        if denominator == 0:
            return 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        return slope

    def calculate_features(
        self,
        cpu_histories: List[PodMetricHistory],
        memory_histories: List[PodMetricHistory],
        restart_counts: Dict[str, int]
    ) -> List[PodFeatures]:
        """Calculate features from CPU history, memory history, and restart counts.

        Handles missing data, single samples, and misaligned metrics.
        """
        pods = set()
        pod_namespaces: Dict[str, str] = {}
        
        cpu_map: Dict[str, List[MetricSample]] = {}
        for h in cpu_histories:
            pods.add(h.pod)
            cpu_map[h.pod] = h.samples
            pod_namespaces[h.pod] = h.namespace

        memory_map: Dict[str, List[MetricSample]] = {}
        for h in memory_histories:
            pods.add(h.pod)
            memory_map[h.pod] = h.samples
            pod_namespaces[h.pod] = h.namespace

        for pod in restart_counts:
            pods.add(pod)

        features_list = []
        for pod in sorted(pods):
            cpu_samples = cpu_map.get(pod, [])
            mem_samples = memory_map.get(pod, [])

            # CPU Feature stats
            if cpu_samples:
                cpu_current = cpu_samples[-1].value
                cpu_average = sum(s.value for s in cpu_samples) / len(cpu_samples)
                cpu_max = max(s.value for s in cpu_samples)
                cpu_min = min(s.value for s in cpu_samples)
                cpu_trend = self._calculate_trend(cpu_samples)
            else:
                cpu_current = cpu_average = cpu_max = cpu_min = cpu_trend = None

            # Memory Feature stats
            if mem_samples:
                memory_current = mem_samples[-1].value
                memory_average = sum(s.value for s in mem_samples) / len(mem_samples)
                memory_max = max(s.value for s in mem_samples)
                memory_min = min(s.value for s in mem_samples)
                memory_trend = self._calculate_trend(mem_samples)
            else:
                memory_current = memory_average = memory_max = memory_min = memory_trend = None

            restarts = restart_counts.get(pod, 0)
            namespace = pod_namespaces.get(pod, "demo")

            features = PodFeatures(
                pod=pod,
                namespace=namespace,
                cpu_current=cpu_current,
                cpu_average=cpu_average,
                cpu_max=cpu_max,
                cpu_min=cpu_min,
                cpu_trend=cpu_trend,
                memory_current=memory_current,
                memory_average=memory_average,
                memory_max=memory_max,
                memory_min=memory_min,
                memory_trend=memory_trend,
                restart_count=restarts
            )
            features_list.append(features)

        return features_list


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KubeGuard AI Feature Service")
    parser.add_argument(
        "--namespace",
        type=str,
        default="demo",
        help="Target namespace to extract features for (default: demo)"
    )
    args = parser.parse_args()

    client = PrometheusClient()
    feature_service = FeatureService(client)
    collector = Collector(client)
    target_namespace = args.namespace

    # Last 15 minutes
    now = time.time()
    start_time = now - 15 * 60
    end_time = now
    step_interval = 60

    print(f"Retrieving historical data from namespace '{target_namespace}'...")
    try:
        # Fetch CPU and Memory history
        cpu_h = feature_service.get_cpu_history(target_namespace, start_time, end_time, step_interval)
        mem_h = feature_service.get_memory_history(target_namespace, start_time, end_time, step_interval)
        
        # Fetch restart counts
        restarts = collector._get_restart_count(target_namespace)

        # Calculate features
        print("Calculating pod features...")
        features_list = feature_service.calculate_features(cpu_h, mem_h, restarts)

        print(f"Successfully calculated features for {len(features_list)} pod(s) in namespace '{target_namespace}':\n")
        for f in features_list:
            print(f"Pod: {f.pod}")
            print(f"Namespace: {f.namespace}")
            print("CPU:")
            print(f"  Current: {f.cpu_current}")
            print(f"  Average: {f.cpu_average}")
            print(f"  Max: {f.cpu_max}")
            print(f"  Min: {f.cpu_min}")
            print(f"  Trend: {f.cpu_trend} (units/sec)")
            print("Memory:")
            print(f"  Current: {f.memory_current}")
            print(f"  Average: {f.memory_average}")
            print(f"  Max: {f.memory_max}")
            print(f"  Min: {f.memory_min}")
            print(f"  Trend: {f.memory_trend} (bytes/sec)")
            print(f"Restarts: {f.restart_count}")
            print()

    except Exception as e:
        print(f"Error during feature calculation: {e}", file=sys.stderr)
        sys.exit(1)
