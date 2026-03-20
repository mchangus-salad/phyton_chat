FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Minimal build deps for Python wheels used by AI/data libraries.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements-agentai.txt /tmp/requirements-agentai.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements-agentai.txt \
    && pip install --no-cache-dir gunicorn

COPY . /app

RUN chmod +x /app/scripts/entrypoint-web.sh

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint-web.sh"]
