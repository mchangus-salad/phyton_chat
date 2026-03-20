#!/usr/bin/env sh
set -eu

INTERVAL_HOURS="${CORPUS_UPDATE_INTERVAL_HOURS:-168}"
if [ -z "${INTERVAL_HOURS}" ]; then
  INTERVAL_HOURS="168"
fi

# Guard against invalid values and keep the loop deterministic.
case "${INTERVAL_HOURS}" in
  ''|*[!0-9]*) INTERVAL_HOURS="168" ;;
esac

if [ "${INTERVAL_HOURS}" -le 0 ]; then
  INTERVAL_HOURS="168"
fi

SLEEP_SECONDS=$((INTERVAL_HOURS * 3600))

echo "[corpus-updater] starting updater loop"
echo "[corpus-updater] interval_hours=${INTERVAL_HOURS} sleep_seconds=${SLEEP_SECONDS}"

sleep 30

while true; do
  echo "[corpus-updater] running auto_update_corpus at $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  if python manage.py auto_update_corpus --max-per-topic 20; then
    echo "[corpus-updater] run completed successfully"
  else
    echo "[corpus-updater] run failed; retrying after interval" >&2
  fi

  sleep "${SLEEP_SECONDS}"
done
