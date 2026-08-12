# Future Scope

The following outlines the roadmap for expanding KubeGuard AI from a local experimental prototype to an enterprise-grade cluster optimization platform:

---

## 1. Persistent Feature Store
Deploy a dedicated database layer (e.g. PostgreSQL or TimescaleDB) to archive history logs:
- Persist calculated `PodFeatures` long term.
- Support offline analytical training loops on historical failure signatures.
- Decouple metrics dependency from Prometheus TSDB retention limits (which typically default to 10-15 days).

---

## 2. Advanced Machine Learning
Transition from simple baseline estimators to robust deep learning models:
- **Autoencoders / LSTMs**: Capture complex spatio-temporal resource signatures to predict failures hours in advance.
- **Supervised Classifiers (XGBoost / Random Forest)**: Train classifiers on real logged historical incident files.

---

## 3. Closed-Loop Remediation
Introduce automated remediation layers:
- Develop a custom **Kubernetes Operator** to reconcile prediction risk recommendations.
- Close the loop by automatically scaling up replica sets or cordoning and restarting leaking/high-risk pods, wrapped under manual operator approvals for safety.

---

## 4. Multi-Cluster Observability
Scale the platform to support multiple environments:
- Leverage federated metrics collections.
- Introduce message queue streaming pipelines (e.g. Apache Kafka + Flink/Spark) to ingest and process metrics data streams in real time across multiple clusters.
