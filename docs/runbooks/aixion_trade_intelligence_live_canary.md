# Aixion Trade Intelligence Live Canary Runbook

## Authority

This is a read-only canary. It must not modify TradeBuilder, ranking, risk, broker, order, or position state.

## Preconditions

- TradeBot main process and Upstox capture have their normal credentials and configuration.
- repository dependencies are installed, including PyArrow for Parquet import;
- `DATA_ROOT` points to the same runtime root used by TradeBot;
- system clock is synchronized;
- enough disk exists for the normal capture plus canonical evidence;
- the candidate lineage writer is enabled.

## 1. Set paths

```bash
cd /Users/madhuram/tradebot
export PYTHONPATH=.
export DATA_ROOT="${DATA_ROOT:-$PWD/.runtime}"
export SESSION_ID="tradebot-live-$(date -u +%Y%m%dT%H%M%SZ)"
export EVIDENCE="$DATA_ROOT/trade_intelligence/$SESSION_ID/events.jsonl"
export LINEAGE="$DATA_ROOT/candidate_lineage/candidate_funnel_$(date -u +%Y%m%d).jsonl"
printf '%s\n' "$SESSION_ID" > "$DATA_ROOT/trade_intelligence/LAST_SESSION_ID"
```

## 2. Build the point-in-time session contract

Resolve the exact index identity from the current Upstox instrument master. Do not copy an old contract into a new trade date.

```bash
python scripts/build_trade_intelligence_session_contract.py \
  --instrument-master "$DATA_ROOT/path/to/complete.json.gz" \
  --trade-date "$(date +%F)" \
  --index-name "Nifty 50" \
  --required-metric index_path \
  --require-capture-instruments \
  --output "$DATA_ROOT/trade_intelligence/$SESSION_ID/session_contract.json"
export SESSION_CONTRACT="$DATA_ROOT/trade_intelligence/$SESSION_ID/session_contract.json"
```

The generated contract records the instrument-master SHA-256. Futures basis or breadth must not be declared until their exact futures identity, pairing-lag authority, and point-in-time constituent weights are supplied.

## 3. Start the observer before TradeBot

```bash
python scripts/run_tradebot_intelligence_observer.py \
  --session-id "$SESSION_ID" \
  --lineage "$LINEAGE" \
  --output "$EVIDENCE" \
  --session-contract "$SESSION_CONTRACT" \
  --defer-finalization
```

Run it in a dedicated terminal or supervised process. The observer tolerates the lineage file not existing yet and waits for complete JSONL rows.

## 4. Run TradeBot and the existing Upstox capture normally

Do not change trading permissions for the canary.

The canary does not start TradeBot, Kite, Upstox, or a broker session itself.

## 5. Stop the observer after the runtime has written its last candidate row

Use `Ctrl-C`. Confirm the evidence ends with `OBSERVER_STOPPED`, not `SESSION_ENDED`.

```bash
python - <<'PY'
import json, os
from pathlib import Path
p=Path(os.environ['EVIDENCE'])
last=json.loads(p.read_text().splitlines()[-1])
print(last['event_type'], last['payload'])
assert last['event_type']=='OBSERVER_STOPPED'
PY
```

## 6. Append exact market evidence

Pass the actual Parquet files produced by the existing capture. In append mode the importer derives exact underlying and selected-option identities from candidate outcome contracts and refuses an unresolved all-instrument import.

```bash
python scripts/import_upstox_parquet.py \
  --append-to "$EVIDENCE" \
  --input "$DATA_ROOT/path/to/first.parquet" \
  --input "$DATA_ROOT/path/to/second.parquet"
```

If no exact candidate instruments can be derived, stop. Do not use `--all-instruments` merely to force the command through.

## 7. Finalize and certify

```bash
python scripts/finalize_trade_intelligence_session.py \
  --events "$EVIDENCE" \
  --output-dir "$DATA_ROOT/trade_intelligence/$SESSION_ID/report"
```

The command returns:

- `0` only for `PIPELINE_OFFLINE_CERTIFIED` on the completed live evidence;
- `3` when evidence or a certification gate fails;
- nonzero for unreadable or structurally invalid input.

The word `OFFLINE` in the verdict means the post-session evidence pipeline was certified. It does not turn the live session into a strategy-edge certification.

## 8. Review required artifacts

```text
$DATA_ROOT/trade_intelligence/$SESSION_ID/events.jsonl
$DATA_ROOT/trade_intelligence/$SESSION_ID/events.checkpoint.json
$DATA_ROOT/trade_intelligence/$SESSION_ID/report/certification.json
$DATA_ROOT/trade_intelligence/$SESSION_ID/report/session_report.json
$DATA_ROOT/trade_intelligence/$SESSION_ID/report/session_report.md
```

Review:

- exact producer reconciliation;
- no look-ahead;
- no sequence gaps;
- exact underlying and option identities;
- two-sided option evidence at every declared outcome horizon;
- no analysis errors;
- observer incidents;
- output classification.

## Fail-closed conditions

Do not relabel or manually override:

```text
INVALID_RESEARCH_CAPTURE
PIPELINE_OFFLINE_REJECTED
LOOKAHEAD_VIOLATION
OUTCOME_EVIDENCE_COMPLETE=false
OUTCOME_CALCULATION_VALID=false
PRODUCER_COUNT_RECONCILIATION_FAILED
```

## Rollback

The canary changes no runtime trading code. Stop the observer and remove only its session directory under `.runtime/trade_intelligence/` if cleanup is required. Preserve rejected evidence until the cause is understood.
