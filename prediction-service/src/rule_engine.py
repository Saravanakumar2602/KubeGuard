import os
import sys
import time
import subprocess
import requests
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

# Resolve paths to import from collector-service, feature-service, and prediction-service
current_dir = os.path.dirname(os.path.abspath(__file__))

collector_src = os.path.abspath(os.path.join(current_dir, "../../collector-service/src"))
if collector_src not in sys.path:
    sys.path.append(collector_src)

feature_src = os.path.abspath(os.path.join(current_dir, "../../feature-service/src"))
if feature_src not in sys.path:
    sys.path.append(feature_src)

from kubeguard_prometheus_client import PrometheusClient

from collector import Collector
from feature_service import FeatureService, PodFeatures, PodMetricHistory, MetricSample
from anomaly_detector import IsolationForestDetector, AnomalyResult


@dataclass
class RiskResult:
    """Represents the final health and risk assessment of a Kubernetes pod."""
    pod: str
    namespace: str
    risk_level: str  # LOW, MEDIUM, HIGH
    risk_score: int  # 0 to 100
    reasons: List[str] = field(default_factory=list)
    recommendation: str = ""


class RuleEngine:
    """Deterministic Rule Engine to evaluate operational and anomaly signals for pods."""

    def __init__(
        self,
        cpu_trend_threshold: float = 0.0001,       # CPU cores per second
        memory_trend_threshold: float = 1000.0,    # Bytes per second
        restart_warning_threshold: int = 1,
        restart_critical_threshold: int = 4,
        # Score weights
        ml_anomaly_weight: int = 40,
        memory_trend_weight: int = 25,
        cpu_trend_weight: int = 20,
        restart_weight: int = 15,
        # Boundaries
        low_medium_boundary: int = 30,
        medium_high_boundary: int = 60
    ) -> None:
        """Initialize RuleEngine with thresholds, weights, and boundaries."""
        self.cpu_trend_threshold = cpu_trend_threshold
        self.memory_trend_threshold = memory_trend_threshold
        self.restart_warning_threshold = restart_warning_threshold
        self.restart_critical_threshold = restart_critical_threshold

        self.ml_anomaly_weight = ml_anomaly_weight
        self.memory_trend_weight = memory_trend_weight
        self.cpu_trend_weight = cpu_trend_weight
        self.restart_weight = restart_weight

        self.low_medium_boundary = low_medium_boundary
        self.medium_high_boundary = medium_high_boundary

    def evaluate(self, features: PodFeatures, anomaly: AnomalyResult | None) -> RiskResult:
        """Evaluate pod features and anomaly status to calculate a risk score and recommendation.

        Args:
            features: PodFeatures calculated metrics.
            anomaly: AnomalyResult from Isolation Forest model.

        Returns:
            A RiskResult containing score, level, reasons, and recommendation.
        """
        reasons = []
        score = 0

        # 1. ML Anomaly Rule
        if anomaly is not None:
            if anomaly.is_anomaly:
                reasons.append("Unusual resource behavior detected by the anomaly model.")
                score += self.ml_anomaly_weight
        
        # 2. Memory Trend Rule
        if features.memory_trend is not None:
            if features.memory_trend > self.memory_trend_threshold:
                reasons.append(
                    f"Memory usage is increasing significantly over time (trend: {features.memory_trend:.2f} bytes/sec)."
                )
                score += self.memory_trend_weight

        # 3. CPU Trend Rule
        if features.cpu_trend is not None:
            if features.cpu_trend > self.cpu_trend_threshold:
                reasons.append(
                    f"CPU usage is increasing significantly over time (trend: {features.cpu_trend:.6f} cores/sec)."
                )
                score += self.cpu_trend_weight

        # 4. Restart Rule
        if features.restart_count is not None:
            if features.restart_count >= self.restart_critical_threshold:
                reasons.append(f"Pod has restarted multiple times (restarts: {features.restart_count}).")
                score += self.restart_weight
            elif features.restart_count >= self.restart_warning_threshold:
                reasons.append(f"Pod has restarted (restarts: {features.restart_count}).")
                # Warning restart gets partial restart penalty (e.g. 5 points)
                score += int(self.restart_weight * 0.33)

        # Ensure score is bounded between 0 and 100
        score = min(max(score, 0), 100)

        # Risk level determination based on configurable boundaries
        if score < self.low_medium_boundary:
            risk_level = "LOW"
        elif score < self.medium_high_boundary:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        # Recommendation Generation
        recommendation = self._generate_recommendation(risk_level, reasons)

        return RiskResult(
            pod=features.pod,
            namespace=features.namespace,
            risk_level=risk_level,
            risk_score=score,
            reasons=reasons,
            recommendation=recommendation
        )

    def _generate_recommendation(self, risk_level: str, reasons: List[str]) -> str:
        """Translate triggered reasons into a human-readable recommendation."""
        if risk_level == "LOW":
            return "All monitored signals are currently within normal ranges."

        has_cpu = any("CPU" in r for r in reasons)
        has_memory = any("Memory" in r or "memory" in r for r in reasons)
        has_restarts = any("restart" in r or "Restart" in r for r in reasons)

        if risk_level == "HIGH":
            rec_parts = []
            if has_memory:
                rec_parts.append("Investigate the workload for sustained memory growth and possible memory leakage.")
            if has_restarts:
                rec_parts.append("Investigate the pod for repeated failures and review application logs.")
            if has_cpu:
                rec_parts.append("Investigate sustained CPU pressure and consider workload scaling after confirming the cause.")
            
            if not rec_parts:
                rec_parts.append("Investigate unusual resource metrics flagged by the anomaly detector.")

            return " ".join(rec_parts)

        else:  # MEDIUM
            rec_parts = []
            if has_cpu:
                rec_parts.append("Monitor CPU usage and investigate the workload if the trend continues.")
            if has_memory:
                rec_parts.append("Monitor memory growth and investigate the workload if the trend continues.")
            if has_restarts:
                rec_parts.append("Monitor container restarts and review application events.")

            if not rec_parts:
                rec_parts.append("Monitor pod resource metrics and verify baseline behavior.")

            return " ".join(rec_parts)


def run_unit_tests():
    print("=== Running Deterministic Unit Tests ===")
    engine = RuleEngine()

    # 1. Healthy pod
    f = PodFeatures(
        pod="healthy-pod", namespace="demo",
        cpu_current=0.01, cpu_average=0.01, cpu_max=0.01, cpu_min=0.01, cpu_trend=0.0,
        memory_current=1e7, memory_average=1e7, memory_max=1e7, memory_min=1e7, memory_trend=0.0,
        restart_count=0
    )
    a = AnomalyResult(pod="healthy-pod", namespace="demo", is_anomaly=False, score=-0.45)
    res = engine.evaluate(f, a)
    print(f"Test 1 (Healthy pod) -> Risk: {res.risk_level}, Score: {res.risk_score}")
    assert res.risk_level == "LOW"
    assert res.risk_score == 0

    # 2. CPU anomaly only (above threshold but no ML anomaly)
    f = PodFeatures(
        pod="cpu-trend-pod", namespace="demo",
        cpu_current=0.1, cpu_average=0.05, cpu_max=0.1, cpu_min=0.01, cpu_trend=0.0005,
        memory_current=1e7, memory_average=1e7, memory_max=1e7, memory_min=1e7, memory_trend=0.0,
        restart_count=0
    )
    res = engine.evaluate(f, None)
    print(f"Test 2 (CPU trend only) -> Risk: {res.risk_level}, Score: {res.risk_score}")
    assert res.risk_level == "LOW"  # Score: 20 < 30
    assert res.risk_score == 20

    # 3. Memory growth only (above threshold)
    f = PodFeatures(
        pod="mem-trend-pod", namespace="demo",
        cpu_current=0.01, cpu_average=0.01, cpu_max=0.01, cpu_min=0.01, cpu_trend=0.0,
        memory_current=2e7, memory_average=1.5e7, memory_max=2e7, memory_min=1e7, memory_trend=5000.0,
        restart_count=0
    )
    res = engine.evaluate(f, None)
    print(f"Test 3 (Memory trend only) -> Risk: {res.risk_level}, Score: {res.risk_score}")
    assert res.risk_level == "LOW"  # Score: 25 < 30
    assert res.risk_score == 25

    # 4. ML anomaly only
    f = PodFeatures(
        pod="ml-anomaly-pod", namespace="demo",
        cpu_current=0.01, cpu_average=0.01, cpu_max=0.01, cpu_min=0.01, cpu_trend=0.0,
        memory_current=1e7, memory_average=1e7, memory_max=1e7, memory_min=1e7, memory_trend=0.0,
        restart_count=0
    )
    a = AnomalyResult(pod="ml-anomaly-pod", namespace="demo", is_anomaly=True, score=-0.6)
    res = engine.evaluate(f, a)
    print(f"Test 4 (ML anomaly only) -> Risk: {res.risk_level}, Score: {res.risk_score}")
    assert res.risk_level == "MEDIUM"  # Score: 40
    assert res.risk_score == 40

    # 5. Multiple signals (ML Anomaly + Memory trend + CPU trend)
    f = PodFeatures(
        pod="multi-signal-pod", namespace="demo",
        cpu_current=0.1, cpu_average=0.05, cpu_max=0.1, cpu_min=0.01, cpu_trend=0.0005,
        memory_current=2e7, memory_average=1.5e7, memory_max=2e7, memory_min=1e7, memory_trend=5000.0,
        restart_count=0
    )
    a = AnomalyResult(pod="multi-signal-pod", namespace="demo", is_anomaly=True, score=-0.6)
    res = engine.evaluate(f, a)
    print(f"Test 5 (Multiple signals) -> Risk: {res.risk_level}, Score: {res.risk_score}")
    assert res.risk_level == "HIGH"  # Score: 40 + 25 + 20 = 85
    assert res.risk_score == 85

    # 6. Repeated restarts (restarts = 5)
    f = PodFeatures(
        pod="restarting-pod", namespace="demo",
        cpu_current=0.01, cpu_average=0.01, cpu_max=0.01, cpu_min=0.01, cpu_trend=0.0,
        memory_current=1e7, memory_average=1e7, memory_max=1e7, memory_min=1e7, memory_trend=0.0,
        restart_count=5
    )
    res = engine.evaluate(f, None)
    print(f"Test 6 (Repeated restarts) -> Risk: {res.risk_level}, Score: {res.risk_score}")
    assert res.risk_score == 15

    # 7. Missing signals (restarts / trends are None)
    f = PodFeatures(
        pod="missing-signals-pod", namespace="demo",
        cpu_current=None, cpu_average=None, cpu_max=None, cpu_min=None, cpu_trend=None,
        memory_current=None, memory_average=None, memory_max=None, memory_min=None, memory_trend=None,
        restart_count=None
    )
    res = engine.evaluate(f, None)
    print(f"Test 7 (Missing signals) -> Risk: {res.risk_level}, Score: {res.risk_score}")
    assert res.risk_level == "LOW"
    assert res.risk_score == 0

    print("=== Deterministic Unit Tests Passed ===\n")


if __name__ == "__main__":
    # First execute the deterministic unit tests
    run_unit_tests()

    # Determine if Prometheus is running locally (Live Integration test)
    try:
        response = requests.get("http://localhost:9090", timeout=2)
        prometheus_running = (response.status_code == 200)
    except requests.exceptions.RequestException:
        prometheus_running = False

    if not prometheus_running:
        print("Prometheus is not running locally. Skipping Live Integration Test.")
        sys.exit(0)

    print("Prometheus connection verified. Starting Live Integration Test...")

    # Path to Kubernetes manifests folder
    manifests_dir = os.path.abspath(os.path.join(current_dir, "../../kubernetes/manifests"))

    client = PrometheusClient()
    feature_service = FeatureService(client)
    collector = Collector(client)
    rule_engine = RuleEngine()

    # 1. Setup Baseline
    res = subprocess.run(["kubectl", "get", "ns", "demo"], capture_output=True)
    if res.returncode != 0:
        print("Creating baseline namespace 'demo' and Nginx deployment...")
        subprocess.run(["kubectl", "create", "ns", "demo"], check=True)
        subprocess.run(["kubectl", "create", "deployment", "demo-nginx", "--image=nginx:alpine", "--replicas=2", "-n", "demo"], check=True)
        time.sleep(15)

    print("Deploying CPU-stress and Memory-growth test workloads...")
    subprocess.run(["kubectl", "delete", "ns", "kubeguard-test", "--ignore-not-found=true"])
    subprocess.run(["kubectl", "apply", "-f", os.path.join(manifests_dir, "test-namespace.yaml")], check=True)
    subprocess.run(["kubectl", "apply", "-f", os.path.join(manifests_dir, "cpu-stress.yaml")], check=True)
    subprocess.run(["kubectl", "apply", "-f", os.path.join(manifests_dir, "memory-growth.yaml")], check=True)

    try:
        # 2. Gather Normal observations and bootstrap training data
        print("Collecting normal features from 'demo' namespace...")
        now = time.time()
        start_time = now - 15 * 60
        cpu_h = feature_service.get_cpu_history("demo", start_time, now, 60)
        mem_h = feature_service.get_memory_history("demo", start_time, now, 60)
        restarts = collector._get_restart_count("demo")
        normal_features = feature_service.calculate_features(cpu_h, mem_h, restarts)

        import random
        training_set = []
        random.seed(42)
        for base_feat in normal_features:
            for i in range(10):
                cpu_noise = random.uniform(0.9, 1.1)
                mem_noise = random.uniform(0.95, 1.05)
                f = PodFeatures(
                    pod=f"{base_feat.pod}-synth-{i}",
                    namespace=base_feat.namespace,
                    cpu_current=base_feat.cpu_current * cpu_noise if base_feat.cpu_current is not None else 0.0,
                    cpu_average=base_feat.cpu_average * cpu_noise if base_feat.cpu_average is not None else 0.0,
                    cpu_max=base_feat.cpu_max * cpu_noise if base_feat.cpu_max is not None else 0.0,
                    cpu_min=base_feat.cpu_min * cpu_noise if base_feat.cpu_min is not None else 0.0,
                    cpu_trend=base_feat.cpu_trend + random.uniform(-1e-6, 1e-6) if base_feat.cpu_trend is not None else 0.0,
                    memory_current=base_feat.memory_current * mem_noise if base_feat.memory_current is not None else 0.0,
                    memory_average=base_feat.memory_average * mem_noise if base_feat.memory_average is not None else 0.0,
                    memory_max=base_feat.memory_max * mem_noise if base_feat.memory_max is not None else 0.0,
                    memory_min=base_feat.memory_min * mem_noise if base_feat.memory_min is not None else 0.0,
                    memory_trend=base_feat.memory_trend + random.uniform(-10, 10) if base_feat.memory_trend is not None else 0.0,
                    restart_count=base_feat.restart_count
                )
                training_set.append(f)

        detector = IsolationForestDetector(contamination=0.1, random_state=42)
        detector.fit(training_set)

        print("Waiting 60 seconds for Prometheus collection...")
        time.sleep(60)

        # 3. Gather Stress observations
        print("Collecting metrics from 'kubeguard-test' namespace...")
        now = time.time()
        start_time = now - 15 * 60
        cpu_stress_h = feature_service.get_cpu_history("kubeguard-test", start_time, now, 60)
        mem_stress_h = feature_service.get_memory_history("kubeguard-test", start_time, now, 60)
        restarts_stress = collector._get_restart_count("kubeguard-test")
        stress_features = feature_service.calculate_features(cpu_stress_h, mem_stress_h, restarts_stress)

        # 4. Evaluate both datasets through ML anomaly and Rule Engine
        print("\n=== Live Workload Assessments ===")
        
        print("\nPredictions for Normal Namespace ('demo'):")
        for f in normal_features:
            anomaly_res = detector.predict(f)
            risk_res = rule_engine.evaluate(f, anomaly_res)
            print(f"Pod: {risk_res.pod}")
            print(f"Namespace: {risk_res.namespace}")
            print(f"Risk Level: {risk_res.risk_level}")
            print(f"Risk Score: {risk_res.risk_score}")
            print(f"Reasons:")
            for r in risk_res.reasons:
                print(f"  - {r}")
            if not risk_res.reasons:
                print("  - None")
            print(f"Recommendation:\n  {risk_res.recommendation}")
            print()

        print("\nPredictions for Stress Namespace ('kubeguard-test'):")
        for f in stress_features:
            anomaly_res = detector.predict(f)
            risk_res = rule_engine.evaluate(f, anomaly_res)
            print(f"Pod: {risk_res.pod}")
            print(f"Namespace: {risk_res.namespace}")
            print(f"Risk Level: {risk_res.risk_level}")
            print(f"Risk Score: {risk_res.risk_score}")
            print(f"Reasons:")
            for r in risk_res.reasons:
                print(f"  - {r}")
            if not risk_res.reasons:
                print("  - None")
            print(f"Recommendation:\n  {risk_res.recommendation}")
            print()

    except Exception as e:
        print(f"Error during live assessment: {e}", file=sys.stderr)
    finally:
        print("Cleaning up stress workloads...")
        subprocess.run(["kubectl", "delete", "ns", "kubeguard-test"], check=True)
