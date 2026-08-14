"""KubeGuard CLI package."""

CLI_VERSION = "0.1.0"
CHART_APP_VERSION = "0.1.5"


DEFAULT_NAMESPACE = "kubeguard"
DEFAULT_RELEASE = "kubeguard"
DEFAULT_CHART_PATH = "helm/kubeguard"
DEFAULT_PROMETHEUS_SVC = "kube-prometheus-stack-prometheus.monitoring.svc:9090"
DEFAULT_ALERTMANAGER_SVC = "kube-prometheus-stack-alertmanager"
DEFAULT_ALERTMANAGER_NS = "monitoring"
