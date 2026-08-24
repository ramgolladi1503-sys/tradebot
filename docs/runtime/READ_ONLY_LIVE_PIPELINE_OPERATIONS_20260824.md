# Canonical Read-Only Live Pipeline Operations

This runbook is metadata-only. It never contains Kite API keys, API secrets,
access tokens, or token contents.

## Authority

Run only from the clean external authority checkout:

```text
/Volumes/TradeBotData/tradebot-readonly-live-authority-0916a95f
```

Bind the exact source SHA before starting:

```sh
export TRADEBOT_COMMIT_SHA="$(git rev-parse HEAD)"
```

The process must inherit the already-governed credential environment. Do not
copy values from a LaunchAgent, plist, shell history, chat, or log into the
repository, runtime artifacts, or command text. If the governed environment is
not available, stop with `CURRENT_SESSION_AUTH=NOT_PROVEN`.

## Preflight

The only broker calls allowed by this pipeline are read-only authentication,
margin health, instrument acquisition, and market-data operations. The
preflight must establish, without printing values:

```text
PROFILE_CALL=PASS
MARGINS_CALL=PASS
CURRENT_INSTRUMENT_AUTHORITY=PASS
BROKER_WRITE_AUTHORITY=false
ORDER_AUTHORITY=false
BROKER_ORDER_CALLS=0
```

The current instrument authority must be captured by the pipeline itself. Do
not supply a historical instrument file or manually claim subscription tokens.

## Canonical operator command

After preflight has supplied the current subscription-token authority, run one
canonical session from the same clean checkout:

```sh
python3 scripts/run_read_only_live_pipeline.py \
  --session-date YYYY-MM-DD \
  --runtime-root /Volumes/TradeBotData/tradebot-live-runtime/YYYY-MM-DD \
  --token-path /path/to/governed/token-file \
  --subscription-token TOKEN \
  --max-runtime-sec SECONDS
```

`TOKEN` is an instrument identifier, not a credential. Never use a credential
or access-token value in this argument. The session must be stopped through
the observer's governed stop path so drain and close artifacts are written.

## Evidence gates

The following artifacts are required before any E2E claim:

- `SESSION_MANIFEST.json`
- `CONSUMERS.json`
- `STRATEGY_REGISTRY.json`
- `SIDECAR_HEALTH.json`
- `consumer_cycle_latest.json`
- `feed_health.json`
- `heartbeat.json`
- `session_exit_gate.json`

Validate without contacting the broker:

```sh
python3 scripts/validate_read_only_live_pipeline.py \
  --runtime-root /Volumes/TradeBotData/tradebot-live-runtime/YYYY-MM-DD \
  --source-sha "$TRADEBOT_COMMIT_SHA" \
  --require-e2e
```

Exit code `2` or `verdict=BLOCKED` is the truthful result when any live gate
is missing. Unit tests, authentication alone, socket connection, requested
subscriptions, or a nonempty candidate file cannot substitute for fresh ticks,
subscription confirmation, advancing canonical persistence, consumer health,
and independently verified close evidence.

