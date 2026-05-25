FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY shared/ /app/shared/
COPY services/worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/worker/app/ /app/app/

EXPOSE 8004

CMD ["python", "-m", "app.main"]
