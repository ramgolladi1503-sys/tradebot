#!/bin/bash
while true; do
  current_time=$(date +%H%M)
  if [ "$current_time" -ge "1530" ]; then
    echo "Market closed. Stopping loop."
    break
  fi
  echo "[LOOP] Starting run_live.sh at $(date)..."
  ./run_live.sh
  exit_code=$?
  echo "[LOOP] run_live.sh exited with code $exit_code."
  if [ "$current_time" -ge "1530" ]; then
    break
  fi
  echo "[LOOP] Restarting in 5 seconds..."
  sleep 5
done
