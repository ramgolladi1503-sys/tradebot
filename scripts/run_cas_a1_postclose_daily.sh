#!/usr/bin/env bash
set -euo pipefail

ROOT="${TRADEBOT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${CAS_A1_PYTHON:-python3}"
TRADE_DATE="${CAS_A1_TRADE_DATE:-$(TZ=Asia/Kolkata date +%F)}"
BUNDLE_ROOT="${CAS_A1_BUNDLE_ROOT:-$ROOT/.runtime/aixion_trade_intelligence/cas_a1/source_bundles}"
EVENT_ROOT="${CAS_A1_EVENT_ROOT:-$ROOT/.runtime/aixion_trade_intelligence}"
OUTPUT_ROOT="${CAS_A1_OUTPUT_ROOT:-$ROOT/.runtime/aixion_trade_intelligence/cas_a1/prospective}"
INBOX_ROOT="${CAS_A1_INBOX_ROOT:-$ROOT/.runtime/aixion_trade_intelligence/cas_a1/inbox}"

BUNDLE="$BUNDLE_ROOT/$TRADE_DATE.json"
OBSERVATION="$INBOX_ROOT/$TRADE_DATE.json"
EVENTS="$EVENT_ROOT/$TRADE_DATE/events.jsonl"

cd "$ROOT"
mkdir -p "$INBOX_ROOT" "$OUTPUT_ROOT" "$(dirname "$EVENTS")"

if [[ ! -s "$BUNDLE" ]]; then
  printf '{"status":"NO_VALID_SESSION_INPUT","trade_date":"%s","bundle":"%s","broker_write_authority":false,"order_authority":false,"paper_authorized":false,"live_authorized":false}\n' "$TRADE_DATE" "$BUNDLE"
  exit 0
fi

PYTHONPATH=. "$PYTHON_BIN" scripts/build_cas_a1_postclose_observation.py \
  --bundle "$BUNDLE" \
  --output "$OBSERVATION"

PYTHONPATH=. "$PYTHON_BIN" scripts/finalize_cas_a1_intelligence_session.py \
  --input "$OBSERVATION" \
  --events "$EVENTS" \
  --output-root "$OUTPUT_ROOT"
