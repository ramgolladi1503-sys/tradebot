# Keltner/Hilega V1 Live Shadow Run

1. Feed only completed five-minute NIFTY, BANKNIFTY and SENSEX candles into the observer.
2. Use a dedicated evidence root and state file.
3. Do not register the observer as a strategy and do not pass its rows to ranking, risk, TradeBuilder or broker paths.
4. At post-close run:

```bash
python scripts/verify_keltner_hm_live_run.py \
  --events <evidence-root>/events.jsonl \
  --output <evidence-root>/live_verdict.json
```

Required before merge:

```text
PASS_LIVE_SHADOW_RUN
zero duplicate event IDs
zero authority violations
zero look-ahead violations from independent timestamp review
clean restart replay
complete session shutdown and evidence seal
```

The first live session proves integration integrity only. It does not prove edge.
