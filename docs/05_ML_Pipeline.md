# Machine Learning Pipeline

KubeGuard AI integrates a hybrid machine learning pipeline combining unsupervised anomaly detection with statistical trend analytics.

---

## 1. Unsupervised Anomaly Detection

### Model: Isolation Forest
An **Isolation Forest** model is implemented to detect resource utilization anomalies without relying on labeled failure data.

- **Library**: `scikit-learn` (`sklearn.ensemble.IsolationForest`)
- **Features**:
  - `cpu_average` (Normalized average CPU utilization)
  - `cpu_trend` (CPU rate slope cores/second)
- **Contamination**: Set to `0.1` (assuming approximately 10% of observations may represent outlying conditions).
- **Training Strategy**: During application initialization, the model trains by bootstrapping a dataset representing baseline normal operations:
  ```python
  # Synthetic baseline normal data generation:
  # CPU average centered around 1.0, memory average around 50MB, zero trends
  cpu_noise = random.uniform(0.9, 1.1)
  mem_noise = random.uniform(45 * 1024 * 1024, 55 * 1024 * 1024)
  # Features: [cpu_current, cpu_average, cpu_max, cpu_min, cpu_trend, memory_current, memory_average, memory_max, memory_min, memory_trend, restart_count]
  ```

---

## 2. Statistical Trend Modeling

To predict gradual degradation (such as memory leaks), we fit an analytical linear regression slope over the historical range query points:

- **Method**: Standard Least-Squares Linear Regression (`numpy.polyfit` or closed-form slope calculator).
- **Inputs**: Time-series list of `MetricSample` points collected over a `15-minute` window with a `60-second` step.
- **Formulas**:
  $$\text{Slope} = \frac{N\sum(xy) - \sum x \sum y}{N\sum(x^2) - (\sum x)^2}$$
- **Threshold Classifications**:
  - **Memory Leak**: Evaluated as a sustained memory growth trend $> 1000$ bytes/second.
  - **CPU Spike**: Evaluated as a positive CPU trend slope $> 0.0001$ cores/second.

---

## 3. Operational Logic Coupling (Rule Engine)

Statistical anomalies are coupled with operational checks to construct the final risk level:

| Target Indicator | Operational Metric | Risk Weight |
|---|---|---|
| **Outlier Resource State** | Isolation Forest flags features anomaly | `+30` score |
| **Active Memory Leak** | Memory growth trend $> 1000$ B/s | `+20` score |
| **High CPU Trend** | CPU trend slope $> 0.0001$ cores/s | `+15` score |
| **Warning Restarts** | Container status restart count $\ge 1$ | `+10` score |
| **Critical Restarts** | Container status restart count $\ge 4$ | `+30` score |
| **Warning Memory Limit** | Current memory usage $> 80\%$ of baseline | `+15` score |

- **Risk Levels**:
  - **LOW**: Score $< 30$ (All systems nominal).
  - **MEDIUM**: Score $30 \le \text{Score} < 60$ (Anomaly detected, monitor closely).
  - **HIGH**: Score $\ge 60$ (Immediate scaling or restart action required).
