import os
import sys
import time
import logging
import threading
from typing import List, Dict

from fastapi import FastAPI, HTTPException, Path, Response
from pydantic import BaseModel, Field
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from config import KubeGuardConfig
from logging_config import setup_logging

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

from kubeguard_prometheus_client import PrometheusClient
from collector import Collector
from feature_service import FeatureService, PodFeatures
from anomaly_detector import IsolationForestDetector, AnomalyResult
from rule_engine import RuleEngine, RiskResult
from metrics import (
    update_pod_metrics,
    kubeguard_pod_predictions_total,
    kubeguard_prediction_duration_seconds,
)
from feature_store import FeatureStore
from model_store import ModelStore

# Global config & logging setup
config = KubeGuardConfig.from_env()
setup_logging(log_level=config.log_level, log_format=config.log_format)
logger = logging.getLogger("kubeguard-api")



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


class ModelInfoResponse(BaseModel):
    source: str = Field(..., description="Model source: bootstrap or historical")
    version: int = Field(..., description="Model version generation number")
    trained_at: str = Field(..., description="ISO timestamp when model was trained")
    training_samples: int = Field(..., description="Number of samples used in training")
    feature_count: int = Field(default=11, description="Number of features evaluated")


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

    def __init__(self, cfg: KubeGuardConfig | None = None) -> None:
        self.config = cfg or KubeGuardConfig.from_env()
        logger.info(f"Initializing PrometheusClient with URL: {self.config.prometheus_url}")


        self.client = PrometheusClient(base_url=self.config.prometheus_url)
        self.collector = Collector(self.client)
        self.feature_service = FeatureService(self.client)
        self.detector = IsolationForestDetector(contamination=0.1, random_state=42)
        self.rule_engine = RuleEngine()

        # Persistent storage & model stores
        self.feature_store = FeatureStore(db_path=self.config.feature_store_path)
        self.model_store = ModelStore(model_path=self.config.model_path)

        # Training threshold & retraining configs
        self.min_training_samples = self.config.min_training_samples
        self.model_retrain_interval_seconds = self.config.model_retrain_interval_seconds
        self.last_retrain_time = 0.0


    def initialize_model(self) -> bool:
        """Initialize Isolation Forest detector from disk artifact, real history, or bootstrap fallback."""
        # 1. Try loading persisted model artifact from disk
        if self.model_store.exists():
            model_obj, meta = self.model_store.load_model()
            if model_obj and meta:
                self.detector.set_fitted_model(model_obj, meta)
                logger.info(
                    f"Loaded persisted Isolation Forest model (version={meta.get('model_version')}, "
                    f"source={meta.get('model_source')}, samples={meta.get('training_sample_count')})"
                )
                return True

        # 2. Check if enough real historical feature observations exist
        sample_count = self.feature_store.count_features()
        if sample_count >= self.min_training_samples:
            logger.info(
                f"Found {sample_count} historical observations (>= threshold {self.min_training_samples}). "
                "Training historical model..."
            )
            return self.train_historical_model()

        # 3. Fallback to bootstrap model
        logger.info(
            f"Historical observations ({sample_count}) < threshold ({self.min_training_samples}). "
            "Initializing bootstrap model fallback..."
        )
        return self._train_bootstrap_model()

    def train_historical_model(self) -> bool:
        """Train Isolation Forest model on stored historical feature vectors."""
        try:
            features = self.feature_store.get_features()
            if not features:
                logger.warning("No historical features available to train model.")
                return False

            X = []
            for f in features:
                try:
                    vec = self.detector._extract_feature_vector(f)
                    X.append(vec)
                except ValueError:
                    continue

            if len(X) < 1:
                logger.warning("No valid feature vectors extracted for historical model fitting.")
                return False

            existing_meta = self.model_store.get_metadata()
            next_version = (existing_meta.get("model_version", 0) + 1) if existing_meta else 1

            self.detector.fit_vectors(X, source="historical", version=next_version)
            self.model_store.save_model(
                self.detector.model,
                training_sample_count=len(X),
                model_source="historical",
                model_version=next_version,
            )
            self.last_retrain_time = time.time()
            logger.info(f"Successfully trained & persisted historical model version {next_version} with {len(X)} samples.")
            return True

        except Exception as e:
            logger.error(f"Error training historical model: {e}")
            return False

    def _train_bootstrap_model(self) -> bool:
        """Train baseline model from demo namespace with synthetic perturbation fallback."""
        try:
            now = time.time()
            start_time = now - 15 * 60

            try:
                self.client.query("up")
            except Exception as conn_err:
                raise PrometheusConnectionError(f"Could not reach Prometheus: {conn_err}")

            cpu_h = self.feature_service.get_cpu_history("demo", start_time, now, 60)
            mem_h = self.feature_service.get_memory_history("demo", start_time, now, 60)
            restarts = self.collector._get_restart_count("demo")
            normal_features = self.feature_service.calculate_features(cpu_h, mem_h, restarts)

            if not normal_features:
                logger.warning("No baseline pods found in 'demo' namespace to fit bootstrap model.")
                return False

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
                        restart_count=base_feat.restart_count,
                    )
                    training_set.append(f)

            existing_meta = self.model_store.get_metadata()
            version = existing_meta.get("model_version", 1) if existing_meta else 1

            self.detector.fit(training_set, source="bootstrap", version=version)
            self.model_store.save_model(
                self.detector.model,
                training_sample_count=len(training_set),
                model_source="bootstrap",
                model_version=version,
            )
            self.last_retrain_time = time.time()
            logger.info("Bootstrap IsolationForest model successfully trained and persisted.")
            return True

        except PrometheusConnectionError as e:
            logger.error(f"Startup model fitting failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during bootstrap model initialization: {e}")
            return False

    def predict(self, namespace: str, pod: str) -> RiskResult:
        """Run the prediction pipeline for a single pod in a namespace.

        Args:
            namespace: The target Kubernetes namespace.
            pod: The target pod name.

        Returns:
            A RiskResult object.
        """
        start_time_pred = time.time()
        try:
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

            # 5. Persist observation to FeatureStore
            try:
                self.feature_store.save_feature(pod_features)
            except Exception as store_err:
                logger.error(f"Error persisting feature observation to FeatureStore: {store_err}")

            # 6. Run anomaly detection and rule engine
            anomaly_res = self.detector.predict(pod_features)
            risk_res = self.rule_engine.evaluate(pod_features, anomaly_res)

            # 7. Update Prometheus metrics
            update_pod_metrics(pod_features, anomaly_res, risk_res)

            duration = time.time() - start_time_pred
            kubeguard_prediction_duration_seconds.labels(namespace=namespace).observe(duration)
            kubeguard_pod_predictions_total.labels(namespace=namespace, result="success").inc()
            return risk_res

        except Exception as e:
            kubeguard_pod_predictions_total.labels(namespace=namespace, result="failure").inc()
            raise e


# -------------------------------------------------------------
# FastAPI Application setup
# -------------------------------------------------------------
app = FastAPI(
    title="KubeGuard AI Prediction Service",
    description="REST API to serve real-time anomaly detection and operational risk scores for Kubernetes pods.",
    version="0.1.4"
)

# Instantiate orchestrator and background worker
from worker import MonitoringWorker

orchestrator = PredictionOrchestrator(config)
worker = MonitoringWorker(orchestrator, config)


@app.on_event("startup")
def startup_event():
    # Log configuration summary
    config.log_summary(logger)
    # Attempt to train baseline model on startup
    orchestrator.initialize_model()
    # Start background monitoring worker
    worker.start()


@app.on_event("shutdown")
def shutdown_event():
    # Stop background monitoring worker
    worker.stop()


# -------------------------------------------------------------
# HTTP Endpoints
# -------------------------------------------------------------
@app.get("/health")
def health():
    """Verify that the FastAPI service is healthy."""
    now = time.time()
    worker_status = "healthy"
    if worker.last_success_timestamp > 0 and (now - worker.last_success_timestamp) > worker.health_timeout:
        worker_status = "degraded"

    return {
        "status": "healthy",
        "worker": worker_status,
        "model_source": orchestrator.detector.model_source,
        "model_version": orchestrator.detector.model_version,
    }


@app.get("/ready")
def ready(response: Response):
    """Readiness endpoint verifying application initialization and background worker state."""
    if worker._thread is not None and worker._thread.is_alive():
        return {"status": "ready"}
    response.status_code = 530
    return {"status": "not ready"}



@app.get(
    "/model",
    response_model=ModelInfoResponse,
    summary="Get active Isolation Forest model metadata."
)
def model_info():
    """Retrieve metadata about the currently active Isolation Forest model."""
    meta = orchestrator.model_store.get_metadata()
    if meta:
        return ModelInfoResponse(
            source=meta.get("model_source", orchestrator.detector.model_source),
            version=meta.get("model_version", orchestrator.detector.model_version),
            trained_at=meta.get("trained_at", orchestrator.detector.trained_at or "unknown"),
            training_samples=meta.get("training_sample_count", orchestrator.detector.training_sample_count),
            feature_count=len(meta.get("feature_names", [])) or 11,
        )
    return ModelInfoResponse(
        source=orchestrator.detector.model_source,
        version=orchestrator.detector.model_version,
        trained_at=orchestrator.detector.trained_at or "unknown",
        training_samples=orchestrator.detector.training_sample_count,
        feature_count=11,
    )



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


@app.get("/metrics")
def metrics():
    """Expose metrics in Prometheus text format."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

