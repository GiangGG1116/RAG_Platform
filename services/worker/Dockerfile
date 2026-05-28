FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY shared/ /app/shared/
COPY services/worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/worker/app/ /app/app/

# Security: run as non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
# Worker needs to write heartbeat file for liveness probe
RUN mkdir -p /tmp && chown appuser:appgroup /tmp
USER appuser

EXPOSE 8004

CMD ["python", "-m", "app.main"]
