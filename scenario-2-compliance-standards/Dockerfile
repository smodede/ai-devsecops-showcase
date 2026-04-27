FROM python:3.11-slim

WORKDIR /app

COPY shared/ ./shared/
COPY scenario-2-compliance-standards/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scenario-2-compliance-standards/ ./scenario-2-compliance-standards/

ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO
EXPOSE 8080

WORKDIR /app/scenario-2-compliance-standards
CMD ["sh", "-c", "PYTHONPATH=/app python -m agent.orchestrator --serve"]
