FROM python:3.11-slim

WORKDIR /app

# Install shared dependencies first (better layer caching)
COPY shared/ ./shared/
COPY scenario-1-build-intelligence/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scenario-1-build-intelligence/ ./scenario-1-build-intelligence/

ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO

WORKDIR /app/scenario-1-build-intelligence
CMD ["sh", "-c", "PYTHONPATH=/app python -m agent.orchestrator"]
