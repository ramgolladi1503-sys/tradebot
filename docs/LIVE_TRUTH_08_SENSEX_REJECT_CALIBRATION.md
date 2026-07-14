# LIVE-TRUTH-08 — SENSEX Reject Calibration Evidence

## Purpose

LIVE-TRUTH-08 adds read-only evidence for SENSEX reject calibration.

The goal is to make SENSEX reject patterns visible when rejection rate, reason concentration, or near-miss rejection share suggests calibration review is needed.

## Scope

In scope:

- SENSEX candidate extraction
- reject reason summary
- reject rate calculation
- dominant reason concentration
- near-miss reject classification
- invalid payload classification
- read-only evidence writing

Out of scope:

- runtime wiring
- UI changes
- ranking changes
- strategy scoring changes
- feed recovery changes
- lifecycle changes

## Module

```text
core/live_truth_sensex_reject_calibration.py
```

Main functions:

```python
build_sensex_reject_calibration_report(...)
write_sensex_reject_calibration_evidence(...)
```

Status values:

- `SENSEX_REJECT_CALIBRATION_BALANCED`
- `SENSEX_REJECT_CALIBRATION_REVIEW`
- `SENSEX_REJECT_CALIBRATION_OVERFILTERED`
- `SENSEX_REJECT_CALIBRATION_BLOCKED`

## Test proof

Focused tests cover:

- balanced SENSEX rejects
- no-candidate evidence
- high reject rate
- concentrated reject reason
- near-miss over-filtering
- miss-ing reject reason
- invalid payload
- invalid config
- non-SENSEX-only payloads
- container extraction
- evidence file writing
- JSON serialization

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_live_truth_08_sensex_reject_calibration.py
```

## Next

After LIVE-TRUTH-08 merges green, continue to LIVE-TRUTH-09 — Runtime Health Artifact Consistency.
