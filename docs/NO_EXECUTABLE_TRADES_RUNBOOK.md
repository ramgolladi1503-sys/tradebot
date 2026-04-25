# No Executable Trades Diagnostic Runbook

## Purpose

Use this runbook when the system produces no executable candidates.

The rule is simple: diagnose first, change code second.

## Command

Run from the repo root:

```bash
python scripts/diagnose_no_executable_trades.py logs/
```

For full JSON output:

```bash
python scripts/diagnose_no_executable_trades.py logs/ --json
```

The script only reads local logs. It does not connect to any broker or external service.

## Output Sections

Review these sections first:

```text
Likely Causes
Top Field Values
Zero Executable Symbols
Recent FINAL EMIT Lines
```

## Main Failure Buckets

### 1. Contract resolution failure

Signals:

```text
CONTRACT_RESOLUTION_FAILED
unresolved_contract
tradingsymbol: None
instrument_token: None
```

Likely area:

```text
contract or instrument lookup logic
```

### 2. Stale market data

Signals:

```text
quote_age_sec is high
LTP missing
bid or ask missing
spread invalid
```

Likely area:

```text
feed, market data, quote freshness, depth snapshot logic
```

### 3. Gating or approval block

Signals:

```text
ADVISORY_ONLY
READY_NOT_APPROVED
execution_allowed: False
primary_blocker exists
```

Likely area:

```text
gating readiness, decision engine, review queue
```

### 4. Ranker produced zero executable candidates

Signal:

```text
TB_RANKED_COUNT_EXECUTABLE count: 0
```

Likely area:

```text
opportunity ranking, decision scoring, candidate normalization
```

### 5. Missing contract identity

Signals:

```text
tradingsymbol missing
instrument_token missing
```

Likely area:

```text
instrument resolution
```

## What To Paste For Review

Paste this output only:

```text
Likely Causes
Top Field Values
Zero Executable Symbols
Recent FINAL EMIT Lines
```

Avoid pasting huge logs first.

## Fix Rules

1. Fix one failure bucket at a time.
2. Do not mix strategy work with execution-readiness debugging.
3. Do not merge unrelated feature branches during this investigation.
4. Add a regression test for every fixed bug.
5. Keep the dashboard status and backend status consistent.

## Done Criteria

This investigation is done only when:

1. The dominant blocker is identified.
2. The blocker has a targeted fix.
3. Tests cover the fixed path.
4. A controlled run shows valid executable candidates.
5. The final status is consistent across logs, review queue, and dashboard.
