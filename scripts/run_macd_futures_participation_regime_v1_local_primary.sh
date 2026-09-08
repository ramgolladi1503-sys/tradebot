#!/usr/bin/env bash
set -euo pipefail

# Read-only retrospective primary-stage execution wrapper.
# It intentionally does not authorize paper/live/broker/order activity.

REPO="${REPO:-/Users/madhuram/tradebot}"
ALIGNED="${ALIGNED:-/Users/madhuram/tradebot/data/research/nifty_futures_alignment_v1/NIFTY_SPOT_FUTURES_ALIGNED_V1.parquet}"
MACD_ROOT="${MACD_ROOT:-/Volumes/TradeBotData/macd_path_dependent_matched_placebo_mechanism_test_v2_20260906T184607Z}"
CANONICAL_ROOT="${CANONICAL_ROOT:-/Volumes/TradeBotData/macd_source_contract_canonical_reimplementation_v1_20260906T134351Z}"
OUTPUT_BASE="${OUTPUT_BASE:-/Volumes/TradeBotData}"
EXPECTED_ALIGNED_SHA="2311981231d3fb847a216c9165ef73c3e7b788ab354d6de493ab1a5edb32e7a9"

ASSIGNMENTS="$MACD_ROOT/MACD_MATCHED_PLACEBO_ASSIGNMENTS.csv"
SIGNAL_PATHS="$MACD_ROOT/MACD_SIGNAL_TRADE_PATH_DECOMPOSITION.csv"
PLACEBO_PAYOFFS="$MACD_ROOT/MACD_MATCHED_PLACEBO_PAYOFF_LEDGER.csv"
PRIMARY_RESULT="$MACD_ROOT/MACD_MATCHED_PLACEBO_PRIMARY_RESULT.json"
ORACLE="$MACD_ROOT/MACD_MATCHED_PLACEBO_INDEPENDENT_ORACLE.json"

for p in \
  "$REPO" "$ALIGNED" "$MACD_ROOT" "$CANONICAL_ROOT" \
  "$ASSIGNMENTS" "$SIGNAL_PATHS" "$PLACEBO_PAYOFFS" "$PRIMARY_RESULT" "$ORACLE"
do
  if [ ! -e "$p" ]; then
    echo "BLOCKED:MISSING_AUTHORITY:$p" >&2
    exit 20
  fi
done

actual_sha="$(shasum -a 256 "$ALIGNED" | awk '{print $1}')"
if [ "$actual_sha" != "$EXPECTED_ALIGNED_SHA" ]; then
  echo "BLOCKED:ALIGNED_SHA_MISMATCH:$actual_sha" >&2
  exit 21
fi

export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"
AUTH_JSON="$(mktemp -t macd_canonical_authority.XXXXXX.json)"
trap 'rm -f "$AUTH_JSON"' EXIT
python3 "$REPO/scripts/resolve_macd_canonical_authority_v1.py" \
  --evidence-root "$CANONICAL_ROOT" \
  --repo-root "$REPO" \
  --output-json "$AUTH_JSON" || {
    echo "BLOCKED:CANONICAL_IMPLEMENTATION_AUTHORITY_UNRESOLVED" >&2
    cat "$AUTH_JSON" >&2 || true
    exit 22
  }

python3 - "$PRIMARY_RESULT" "$ORACLE" <<'PY'
import json, math, sys
primary = json.load(open(sys.argv[1]))
oracle = json.load(open(sys.argv[2]))

def first(obj, *keys):
    for k in keys:
        if k in obj:
            return obj[k]
    return None

n = first(primary, "signal_trade_count", "signal_n")
delta = first(primary, "delta_mean_net_6bps", "delta_net_6bps")
if n is None or int(n) != 148:
    raise SystemExit(f"BLOCKED:CANONICAL_SIGNAL_COUNT_MISMATCH:{n}")
if delta is None or not math.isfinite(float(delta)):
    raise SystemExit("BLOCKED:CANONICAL_DELTA_MISSING")
if not (9.0 <= float(delta) <= 13.0):
    raise SystemExit(f"BLOCKED:CANONICAL_DELTA_UNEXPECTED:{delta}")
status = str(first(oracle, "status", "verdict", "oracle_status") or "").upper()
if "PASS" not in status:
    raise SystemExit(f"BLOCKED:CANONICAL_ORACLE_NOT_PASS:{status}")
print(
    f"CANONICAL_MACD_BOUND=true SIGNAL_N={int(n)} "
    f"DELTA_NET_6BPS={float(delta):.6f} ORACLE={status}"
)
PY

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUTPUT_BASE/macd_futures_participation_regime_v1_primary_${stamp}"
mkdir -p "$OUT"
cp "$AUTH_JSON" "$OUT/CANONICAL_IMPLEMENTATION_AUTHORITY.json"

python3 "$REPO/scripts/run_macd_futures_participation_regime_v1.py" \
  --aligned-parquet "$ALIGNED" \
  --assignments "$ASSIGNMENTS" \
  --signal-paths "$SIGNAL_PATHS" \
  --placebo-payoffs "$PLACEBO_PAYOFFS" \
  --output-root "$OUT"

printf '\nRESULT_ROOT=%s\n' "$OUT"
for f in \
  CANONICAL_IMPLEMENTATION_AUTHORITY.json \
  H1_STATE_SUPPORT.json H1_PRIMARY_RESULT.json \
  H2_STATE_SUPPORT.json H2_PRIMARY_RESULT.json \
  PRIMARY_STAGE_VERDICT.json
do
  if [ -f "$OUT/$f" ]; then
    echo "===== $f ====="
    python3 -m json.tool "$OUT/$f"
  fi
done

python3 - "$OUT/SAFETY.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
required = {
    "buy_only": True,
    "broker_write_authority": False,
    "order_authority": False,
    "paper_authorized": False,
    "live_authorized": False,
    "broker_calls": 0,
    "orders": 0,
    "structural_edge_certified": False,
}
for k, v in required.items():
    if s.get(k) != v:
        raise SystemExit(f"BLOCKED:SAFETY_INVARIANT_FAIL:{k}:{s.get(k)!r}")
print("SAFETY_INVARIANTS=PASS")
PY
