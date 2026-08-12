import sys
from dataclasses import dataclass
from typing import List, Dict, Tuple
from kubeguard_prometheus_client import PrometheusClient



@dataclass
class PodMetrics:
    """Represents the structured metrics collected for a Kubernetes pod."""
    pod: str
    namespace: str
    cpu_usage: float
    memory_usage: float
    restart_count: int


class Collector:
    """Collector for Kubernetes pod performance and status metrics from Prometheus."""

    def __init__(self, prometheus_client: PrometheusClient) -> None:
        """Initialize the Collector with a PrometheusClient instance.

        Args:
            prometheus_client: An instance of PrometheusClient.
        """
        self.client = prometheus_client

    def _discover_pods(self, namespace: str) -> List[Tuple[str, str]]:
        """Discover pods in the specified namespace.

        Returns:
            A list of tuples, each containing (pod_name, namespace).
        """
        query = f'kube_pod_info{{namespace="{namespace}"}}'
        data = self.client.query(query)
        pods = []
        for item in data.get("result", []):
            metric = item.get("metric", {})
            pod_name = metric.get("pod")
            ns = metric.get("namespace")
            if pod_name and ns:
                pods.append((pod_name, ns))
        return pods

    def _get_cpu_usage(self, namespace: str) -> Dict[str, float]:
        """Query CPU usage for pods in the namespace.

        Returns:
            A dictionary mapping pod name to CPU usage.
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
        data = self.client.query(query)
        cpu_usage = {}
        for item in data.get("result", []):
            pod = item.get("metric", {}).get("pod")
            value = item.get("value")
            if pod and value and len(value) > 1:
                try:
                    cpu_usage[pod] = float(value[1])
                except (ValueError, TypeError):
                    cpu_usage[pod] = 0.0
        return cpu_usage

    def _get_memory_usage(self, namespace: str) -> Dict[str, float]:
        """Query Memory usage (working set bytes) for pods in the namespace.

        Returns:
            A dictionary mapping pod name to memory usage in bytes.
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
        data = self.client.query(query)
        memory_usage = {}
        for item in data.get("result", []):
            pod = item.get("metric", {}).get("pod")
            value = item.get("value")
            if pod and value and len(value) > 1:
                try:
                    memory_usage[pod] = float(value[1])
                except (ValueError, TypeError):
                    memory_usage[pod] = 0.0
        return memory_usage

    def _get_restart_count(self, namespace: str) -> Dict[str, int]:
        """Query container restart counts for pods in the namespace.

        Returns:
            A dictionary mapping pod name to restart count.
        """
        query = (
            f'sum by (pod, namespace) ('
            f'  kube_pod_container_status_restarts_total{{namespace="{namespace}"}}'
            f')'
        )
        data = self.client.query(query)
        restart_counts = {}
        for item in data.get("result", []):
            pod = item.get("metric", {}).get("pod")
            value = item.get("value")
            if pod and value and len(value) > 1:
                try:
                    restart_counts[pod] = int(float(value[1]))
                except (ValueError, TypeError):
                    restart_counts[pod] = 0
        return restart_counts

    def collect(self, namespace: str = "demo") -> List[PodMetrics]:
        """Discover pods and collect CPU, memory, and restarts metrics for a namespace.

        Args:
            namespace: The target Kubernetes namespace.

        Returns:
            A list of PodMetrics objects containing performance data for each pod.
        """
        # 1. Discover pods
        pods = self._discover_pods(namespace)
        if not pods:
            return []

        # 2. Query other metrics
        cpu_usage_map = self._get_cpu_usage(namespace)
        memory_usage_map = self._get_memory_usage(namespace)
        restart_count_map = self._get_restart_count(namespace)

        # 3. Match metrics by pod name and build PodMetrics list
        collected_metrics = []
        for pod_name, ns in pods:
            cpu = cpu_usage_map.get(pod_name, 0.0)
            memory = memory_usage_map.get(pod_name, 0.0)
            restarts = restart_count_map.get(pod_name, 0)
            
            pod_metric = PodMetrics(
                pod=pod_name,
                namespace=ns,
                cpu_usage=cpu,
                memory_usage=memory,
                restart_count=restarts
            )
            collected_metrics.append(pod_metric)

        return collected_metrics


if __name__ == "__main__":
    client = PrometheusClient()
    collector = Collector(client)
    target_namespace = "demo"
    print(f"Collecting pod metrics from namespace: '{target_namespace}'...")
    try:
        metrics = collector.collect(namespace=target_namespace)
        print(f"Successfully collected metrics for {len(metrics)} pod(s):\n")
        for m in metrics:
            print(f"Pod: {m.pod}")
            print(f"Namespace: {m.namespace}")
            print(f"CPU: {m.cpu_usage}")
            print(f"Memory: {m.memory_usage}")
            print(f"Restarts: {m.restart_count}")
            print()
    except Exception as e:
        print(f"Error during metrics collection: {e}", file=sys.stderr)
        sys.exit(1)
