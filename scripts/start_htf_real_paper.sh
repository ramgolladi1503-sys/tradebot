#!/usr/bin/env bash
set -euo pipefail

cd /Users/madhuram/tradebot

mkdir -p logs runtime/candidate_audits

nohup python -u scripts/run_htf_real_paper_monitor.py \
  > logs/htf_real_paper_monitor_$(date +%Y%m%d).log 2>&1 &

echo $! > runtime/candidate_audits/htf_real_paper_monitor.pid
echo "Started HTF real-paper monitor PID=$(cat runtime/candidate_audits/htf_real_paper_monitor.pid)"
