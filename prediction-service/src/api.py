import os
import sys
import time
import logging
from typing import List, Dict
from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kubeguard-api")

# Resolve paths to import from collector-service, feature-service, and prediction-service
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

collector_src = os.path.abspath(os.path.join(current_dir, "../../collector-service/src"))
if collector_src not in sys.path:
    sys.path.append(collector_src)

feature_src = os.path.abspath(os.path.join(current_dir, "../../feature-service/src"))
if feature_src not in sys.path:
    sys.path.append(feature_src)


from prometheus_client import PrometheusClient
from collector import Collector
from feature_service import FeatureService, PodFeatures
from anomaly_detector import IsolationForestDetector, AnomalyResult
from rule_engine import RuleEngine, RiskResult


# -------------------------------------------------------------
# Pydantic Schemas
# -------------------------------------------------------------
class RiskPredictionResponse(BaseModel):
    pod: str = Field(..., description="The name of the pod")
    namespace: str = Field(..., description="The namespace of the pod")
    risk_level: str = Field(..., description="Calculated risk level: LOW, MEDIUM, or HIGH")
    risk_score: int = Field(..., description="Operational risk score between 0 and 100")
    reasons: List[str] = Field(default_factory=list, description="Triggered reasons for the risk score")
    recommendation: str = Field(..., description="Human-readable advisory recommendation")


# -------------------------------------------------------------
# Custom Exceptions
# -------------------------------------------------------------
class PodNotFoundError(Exception):
    pass


class PrometheusConnectionError(Exception):
    pass


# -------------------------------------------------------------
# Service / Orchestration Layer
# -------------------------------------------------------------
class PredictionOrchestrator:
    """Orchestrator to coordinate metrics collection, feature calculation, ML anomaly detection, and risk rules."""

    def __init__(self) -> None:
        # Configuration
        prometheus_url = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
        logger.info(f"Initializing PrometheusClient with URL: {prometheus_url}")

        self.client = PrometheusClient(base_url=prometheus_url)
        self.collector = Collector(self.client)
        self.feature_service = FeatureService(self.client)
        self.detector = IsolationForestDetector(contamination=0.1, random_state=42)
        self.rule_engine = RuleEngine()

    def initialize_model(self) -> bool:
        """Fetch baseline normal metrics and fit the Isolation Forest model on startup or on-demand.

        Returns:
            True if successfully trained, False otherwise.
        """
        try:
            logger.info("Initializing baseline model on 'demo' namespace...")
            now = time.time()
            start_time = now - 15 * 60

            # Verify Prometheus connectivity
            try:
                self.client.query("up")
            except Exception as conn_err:
                raise PrometheusConnectionError(f"Could not reach Prometheus: {conn_err}")

            cpu_h = self.feature_service.get_cpu_history("demo", start_time, now, 60)
            mem_h = self.feature_service.get_memory_history("demo", start_time, now, 60)
            restarts = self.collector._get_restart_count("demo")
            normal_features = self.feature_service.calculate_features(cpu_h, mem_h, restarts)

            if not normal_features:
                logger.warning("No baseline pods found in 'demo' namespace to fit model.")
                return False

            # Bootstrap training dataset with synthetic normal observations (perturbation-based)
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

            self.detector.fit(training_set)
            logger.info("Baseline IsolationForest model successfully trained.")
            return True

        except PrometheusConnectionError as e:
            logger.error(f"Startup model fitting failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during model initialization: {e}")
            return False

    def predict(self, namespace: str, pod: str) -> RiskResult:
        """Run the prediction pipeline for a single pod in a namespace.

        Args:
            namespace: The target Kubernetes namespace.
            pod: The target pod name.

        Returns:
            A RiskResult object.
        """
        # 1. Verify Prometheus availability
        try:
            self.client.query("up")
        except Exception as conn_err:
            raise PrometheusConnectionError(f"Prometheus is unreachable: {conn_err}")

        # 2. Verify Pod existence
        pods = self.collector._discover_pods(namespace)
        pod_names = [p[0] for p in pods]
        if pod not in pod_names:
            raise PodNotFoundError(f"Pod '{pod}' not found in namespace '{namespace}'")

        # 3. Handle model fit fallback on-demand
        if not self.detector.is_fitted:
            logger.info("Model not trained yet. Trying to fit model on-demand...")
            trained = self.initialize_model()
            if not trained:
                raise RuntimeError("Failed to initialize baseline anomaly model. Cannot perform prediction.")

        # 4. Fetch metrics and compute features
        now = time.time()
        start_time = now - 15 * 60
        cpu_h = self.feature_service.get_cpu_history(namespace, start_time, now, 60)
        mem_h = self.feature_service.get_memory_history(namespace, start_time, now, 60)
        restarts = self.collector._get_restart_count(namespace)

        features_list = self.feature_service.calculate_features(cpu_h, mem_h, restarts)
        
        # Match current pod features
        pod_features = None
        for f in features_list:
            if f.pod == pod:
                pod_features = f
                break

        if not pod_features:
            raise PodNotFoundError(f"No metric feature history found for pod '{pod}' in namespace '{namespace}'")

        # 5. Run anomaly detection and rule engine
        anomaly_res = self.detector.predict(pod_features)
        risk_res = self.rule_engine.evaluate(pod_features, anomaly_res)

        return risk_res


# -------------------------------------------------------------
# FastAPI Application setup
# -------------------------------------------------------------
app = FastAPI(
    title="KubeGuard AI Prediction Service",
    description="REST API to serve real-time anomaly detection and operational risk scores for Kubernetes pods.",
    version="1.0.0"
)

# Instantiate orchestrator
orchestrator = PredictionOrchestrator()


@app.on_event("startup")
def startup_event():
    # Attempt to train baseline model on startup
    orchestrator.initialize_model()


# -------------------------------------------------------------
# HTTP Endpoints
# -------------------------------------------------------------
@app.get("/health")
def health():
    """Verify that the FastAPI service is healthy."""
    return {"status": "healthy"}


@app.get(
    "/predict/{namespace}/{pod}",
    response_model=RiskPredictionResponse,
    summary="Get risk assessment for a specific pod."
)
def predict(
    namespace: str = Path(..., min_length=1, description="Kubernetes namespace"),
    pod: str = Path(..., min_length=1, description="Kubernetes pod name")
):
    """Retrieve features, run anomaly detection, evaluate rules, and return risk assessment."""
    try:
        risk_res = orchestrator.predict(namespace=namespace, pod=pod)
        return RiskPredictionResponse(
            pod=risk_res.pod,
            namespace=risk_res.namespace,
            risk_level=risk_res.risk_level,
            risk_score=risk_res.risk_score,
            reasons=risk_res.reasons,
            recommendation=risk_res.recommendation
        )

    except PodNotFoundError as e:
        logger.warning(str(e))
        raise HTTPException(status_code=404, detail=str(e))

    except PrometheusConnectionError as e:
        logger.error(str(e))
        raise HTTPException(
            status_code=503,
            detail="Required monitoring backend (Prometheus) is unreachable. Verify port-forward or connection parameters."
        )

    except Exception as e:
        logger.error(f"Unexpected prediction error: {e}")
        raise HTTPException(status_code=500, detail="An unexpected internal prediction error occurred.")
