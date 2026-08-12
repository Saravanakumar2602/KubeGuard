import os
import sys
import time
import subprocess
from dataclasses import dataclass
from typing import List, Dict

# Resolve paths to import from collector-service and feature-service
current_dir = os.path.dirname(os.path.abspath(__file__))

collector_src = os.path.abspath(os.path.join(current_dir, "../../collector-service/src"))
if collector_src not in sys.path:
    sys.path.append(collector_src)

feature_src = os.path.abspath(os.path.join(current_dir, "../../feature-service/src"))
if feature_src not in sys.path:
    sys.path.append(feature_src)

from prometheus_client import PrometheusClient
from collector import Collector
from feature_service import FeatureService, PodFeatures, MetricSample, PodMetricHistory

# Import scikit-learn
from sklearn.ensemble import IsolationForest


@dataclass
class AnomalyResult:
    """Represents the anomaly detection result for a pod observation."""
    pod: str
    namespace: str
    is_anomaly: bool
    score: float  # Raw Isolation Forest anomaly score


class IsolationForestDetector:
    """Isolation Forest based anomaly detector for Kubernetes pod resource metrics."""

    def __init__(self, contamination: str | float = "auto", random_state: int = 42) -> None:
        """Initialize the detector with model configuration.

        Args:
            contamination: The amount of contamination of the data set.
            random_state: Random state for reproducibility.
        """
        self.contamination = contamination
        self.random_state = random_state
        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=self.random_state
        )
        self.is_fitted = False

    def _extract_feature_vector(self, f: PodFeatures) -> List[float]:
        """Extract a clean numerical feature vector from PodFeatures.

        Raises:
            ValueError: If any required feature is None (incomplete observation).
        """
        features = [
            f.cpu_current,
            f.cpu_average,
            f.cpu_max,
            f.cpu_min,
            f.cpu_trend,
            f.memory_current,
            f.memory_average,
            f.memory_max,
            f.memory_min,
            f.memory_trend,
            float(f.restart_count)
        ]

        # Validation: Reject observations with missing features
        for i, val in enumerate(features):
            if val is None:
                raise ValueError(
                    f"Incomplete observation for pod '{f.pod}'. "
                    f"Feature index {i} is None. All features must be fully populated."
                )
        return features

    def fit(self, training_features: List[PodFeatures]) -> None:
        """Train the Isolation Forest model on a set of normal observations.

        Args:
            training_features: A list of normal PodFeatures observations.
        """
        if not training_features:
            raise ValueError("Training features list cannot be empty.")

        X = []
        for f in training_features:
            X.append(self._extract_feature_vector(f))

        self.model.fit(X)
        self.is_fitted = True

    def predict(self, observation: PodFeatures) -> AnomalyResult:
        """Predict if a single pod observation is anomalous.

        Args:
            observation: The PodFeatures to analyze.

        Returns:
            An AnomalyResult object.
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before calling predict.")

        X_test = [self._extract_feature_vector(observation)]

        # predict returns -1 for anomalies, 1 for normal
        pred = self.model.predict(X_test)[0]
        is_anomaly = bool(pred == -1)

        # score_samples returns raw anomaly score (negative means more anomalous)
        raw_score = float(self.model.score_samples(X_test)[0])

        return AnomalyResult(
            pod=observation.pod,
            namespace=observation.namespace,
            is_anomaly=is_anomaly,
            score=raw_score
        )


if __name__ == "__main__":
    # Path to Kubernetes manifests folder
    manifests_dir = os.path.abspath(os.path.join(current_dir, "../../kubernetes/manifests"))

    # Make sure port-forward is active before running this test script externally
    client = PrometheusClient()
    feature_service = FeatureService(client)
    collector = Collector(client)

    # 1. Setup Namespace/Nginx baseline if not present
    res = subprocess.run(["kubectl", "get", "ns", "demo"], capture_output=True)
    if res.returncode != 0:
        print("Creating baseline namespace 'demo' and Nginx deployment...")
        subprocess.run(["kubectl", "create", "ns", "demo"], check=True)
        subprocess.run(["kubectl", "create", "deployment", "demo-nginx", "--image=nginx:alpine", "--replicas=2", "-n", "demo"], check=True)
        print("Waiting 15 seconds for baseline to pull...")
        time.sleep(15)

    print("Deploying CPU-stress and Memory-growth test workloads...")
    # Clean up previous kubeguard-test runs if left over
    subprocess.run(["kubectl", "delete", "ns", "kubeguard-test", "--ignore-not-found=true"])
    
    # Deploy workloads
    subprocess.run(["kubectl", "apply", "-f", os.path.join(manifests_dir, "test-namespace.yaml")], check=True)
    subprocess.run(["kubectl", "apply", "-f", os.path.join(manifests_dir, "cpu-stress.yaml")], check=True)
    subprocess.run(["kubectl", "apply", "-f", os.path.join(manifests_dir, "memory-growth.yaml")], check=True)

    # 2. Gather Normal observations
    print("Collecting baseline normal metrics from 'demo' namespace...")
    now = time.time()
    start_time = now - 15 * 60
    
    try:
        cpu_h = feature_service.get_cpu_history("demo", start_time, now, 60)
        mem_h = feature_service.get_memory_history("demo", start_time, now, 60)
        restarts = collector._get_restart_count("demo")
        normal_features = feature_service.calculate_features(cpu_h, mem_h, restarts)
        
        if not normal_features:
            raise ValueError("No baseline pods found. Ensure 'demo-nginx' pods are running in 'demo' namespace.")

        # 3. Bootstrap training dataset with synthetic normal observations (perturbation-based)
        print(f"Bootstrapping a training set of 20 normal observations from baseline features...")
        import random
        training_set = []
        random.seed(42)
        
        for base_feat in normal_features:
            for i in range(10):
                # Small fluctuations within normal baseline (CPU +/-10%, Memory +/-5%)
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

        # 4. Train the model
        print("Training IsolationForestDetector baseline model...")
        detector = IsolationForestDetector(contamination=0.1, random_state=42)
        detector.fit(training_set)
        print("Model training complete.")

        # 5. Wait for Prometheus to gather stress workload metrics
        print("Waiting 60 seconds for Prometheus to collect metrics on stress pods...")
        time.sleep(60)

        # 6. Gather Stress observations
        print("Collecting metrics from 'kubeguard-test' namespace...")
        now = time.time()
        start_time = now - 15 * 60
        cpu_stress_h = feature_service.get_cpu_history("kubeguard-test", start_time, now, 60)
        mem_stress_h = feature_service.get_memory_history("kubeguard-test", start_time, now, 60)
        restarts_stress = collector._get_restart_count("kubeguard-test")
        stress_features = feature_service.calculate_features(cpu_stress_h, mem_stress_h, restarts_stress)

        # 7. Run predictions
        print("\nPredictions for Normal Pods:")
        for f in normal_features:
            res = detector.predict(f)
            print(f"Pod: {res.pod}")
            print(f"Namespace: {res.namespace}")
            print(f"Anomaly: {res.is_anomaly}")
            print(f"Score: {res.score:.4f}\n")

        print("\nPredictions for Stress Pods:")
        for f in stress_features:
            res = detector.predict(f)
            print(f"Pod: {res.pod}")
            print(f"Namespace: {res.namespace}")
            print(f"Anomaly: {res.is_anomaly}")
            print(f"Score: {res.score:.4f}\n")

    except Exception as e:
        print(f"Error during execution: {e}", file=sys.stderr)
    finally:
        print("Cleaning up stress workloads...")
        subprocess.run(["kubectl", "delete", "ns", "kubeguard-test"], check=True)
