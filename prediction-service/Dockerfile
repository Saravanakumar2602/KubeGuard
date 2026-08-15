# Use Python 3.11 slim base image (much faster wheel installation than alpine for numpy/scipy/scikit-learn)
FROM python:3.11-slim

WORKDIR /app

# Install dependencies with increased timeout to handle slow networks
COPY prediction-service/requirements.txt /app/prediction-service/requirements.txt
RUN pip install --default-timeout=1000 --no-cache-dir -r /app/prediction-service/requirements.txt

# Copy components
COPY collector-service/src /app/collector-service/src
COPY feature-service/src /app/feature-service/src
COPY prediction-service/src /app/prediction-service/src

# Set PYTHONPATH so prediction-service can find sibling modules
ENV PYTHONPATH="/app/collector-service/src:/app/feature-service/src:/app/prediction-service/src"

# Create non-root application user and ensure data volume directory permissions
RUN groupadd -g 10001 kubeguard && \
    useradd -u 10001 -g kubeguard -s /bin/sh -m kubeguard && \
    mkdir -p /data && \
    chown -R kubeguard:kubeguard /app /data

# Set workdir to prediction-service/src and switch to non-root user
WORKDIR /app/prediction-service/src
USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]

