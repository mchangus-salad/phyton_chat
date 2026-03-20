#!/usr/bin/env sh
set -eu

echo "[entrypoint] running migrations"
python manage.py migrate --noinput

echo "[entrypoint] starting gunicorn"
exec gunicorn webapi.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers ${GUNICORN_WORKERS:-2} \
  --threads ${GUNICORN_THREADS:-4} \
  --timeout ${GUNICORN_TIMEOUT:-120}
