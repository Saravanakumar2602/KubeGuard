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

# Set workdir to prediction-service/src
WORKDIR /app/prediction-service/src

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
