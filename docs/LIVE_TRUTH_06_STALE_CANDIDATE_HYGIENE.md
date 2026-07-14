# LIVE-TRUTH-06 — Stale Candidate Hygiene Guard

## Purpose

LIVE-TRUTH-06 adds read-only evidence for stale candidate hygiene.

Candidates can look usable while carrying old timestamps, stale quote age, stale feed age, stale source artifact age, or explicit stale markers. This PR makes that visible before later ranking, lifecycle, or readiness work consumes candidate evidence.

## Scope

In scope:

- Evaluate candidate timestamp freshness.
- Detect miss_ing candidate timestamps.
- Detect future candidate timestamps.
- Detect stale quote age.
- Detect stale feed age.
- Detect stale source artifact age.
- Detect explicit stale markers.
- Support candidate containers such as `top_opportunities`.
- Emit read-only hygiene evidence.

Out of scope:

- Ranking changes.
- Runtime wiring.
- Dashboard changes.
- Feed reconnect changes.
- Strategy scoring changes.
- Strategy lifecycle changes.

## Module

```text
core/live_truth_stale_candidate_hygiene.py
```

Main functions:

```python
build_stale_candidate_hygiene_report(...)
write_stale_candidate_hygiene_evidence(...)
```

Status values:

- `STALE_CANDIDATE_HYGIENE_CLEAN`
- `STALE_CANDIDATE_HYGIENE_STALE`
- `STALE_CANDIDATE_HYGIENE_BLOCKED`

Reason codes include:

- `candidate_hygiene_clean`
- `no_candidates`
- `invalid_candidate_payload`
- `miss_ing_candidate_timestamp`
- `candidate_timestamp_in_future`
- `stale_candidate_timestamp`
- `stale_candidate_quote`
- `stale_candidate_feed`
- `stale_candidate_source_artifact`
- `candidate_contains_stale_marker`
- `invalid_stale_candidate_hygiene_config`

## Test proof

Focused tests cover:

- clean candidates
- no candidates
- stale candidate timestamp
- missing timestamp
- invalid candidate payload
- future timestamp
- stale quote, feed, and source artifact ages
- explicit stale marker
- ISO timestamps
- container extraction
- invalid config
- evidence file writing
- JSON serialization

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_live_truth_06_stale_candidate_hygiene.py
```

## Next

After LIVE-TRUTH-06 merges green, continue to LIVE-TRUTH-07 — Latency / SLO Guard Oscillation Evidence.
