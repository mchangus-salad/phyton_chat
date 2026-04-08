#!/usr/bin/env sh
set -eu

echo "[entrypoint] running migrations"
python manage.py migrate --noinput

echo "[entrypoint] seeding subscription plans"
python manage.py seed_subscription_plans

echo "[entrypoint] starting gunicorn (ASGI + uvicorn workers for streaming support)"
exec gunicorn webapi.asgi:application \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --workers ${GUNICORN_WORKERS:-2} \
  --timeout ${GUNICORN_TIMEOUT:-120}
