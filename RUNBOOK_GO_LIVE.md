# Go-Live Runbook (Fail-Closed)

## 1) Pre-flight checks

Run from repo root:

```bash
PYTHONPATH=. ./scripts/ci_sanity.sh
PYTHONPATH=. python scripts/check_kite_auth.py
PYTHONPATH=. python scripts/readiness_gate.py
```

Required before any live run:

- readiness `can_trade=true`
- no active risk halt (`logs/risk_halt.json` halted=false)
- feed freshness healthy while market is open
- governance snapshot allows trading (`logs/trading_allowed_snapshot.json`)

## 2) Paper-first validation (minimum 15 minutes)

Run in paper mode first:

```bash
export EXECUTION_MODE=PAPER
PYTHONPATH=. python main.py
```

Acceptance criteria:

- No `RUN_LOCK_ACTIVE` loops
- No repeated websocket restart storms
- `logs/trading_allowed_snapshot.json` reasons are empty during healthy market-open intervals
- Order intents present but no live placement

## 3) Live enablement

Only after paper acceptance:

```bash
export EXECUTION_MODE=LIVE
export ALLOW_LIVE_PLACEMENT=true
PYTHONPATH=. python main.py
```

Operational note:

- Trading remains fail-closed if governance gate reasons are non-empty.

## 4) Kill switch

Immediate hard stop:

```bash
./scripts/kill_switch.sh
```

Recovery after investigation:

```bash
PYTHONPATH=. python scripts/reset_risk_halt.py
PYTHONPATH=. python scripts/readiness_gate.py
```
