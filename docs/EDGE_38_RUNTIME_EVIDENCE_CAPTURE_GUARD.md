# EDGE-38 — Runtime Evidence Capture Guard

## Purpose

EDGE-38 makes live diagnostic evidence packs repeatably diagnosable.

Before this PR, runtime diagnosis could still depend on pasted terminal output and manual inspection. This PR adds a deterministic guard report that validates whether a `runtime/evidence/live_diag_*` directory or `.tar.gz` bundle can produce the required diagnosis sections.

## Required diagnosis sections

The guard requires these sections:

1. `feed`
2. `freshness`
3. `fallback`
4. `candidate_funnel`
5. `score_flattening`
6. `final_no_trade_reasons`

A report is `CAPTURE_GUARD_OK` only when all required sections are covered.

## Implementation

- `core/runtime_evidence_capture_guard.py`
  - wraps the existing EDGE-37 evidence replay analyzer
  - produces `RuntimeEvidenceCaptureGuardReport`
  - verifies required sections
  - preserves safety metadata in `to_dict()`
- `scripts/guard_runtime_evidence_capture.py`
  - CLI for markdown or JSON output
  - optional `--fail-on-incomplete` for gates
- `tests/test_runtime_evidence_capture_guard.py`
  - proves complete evidence pack coverage
  - proves `.tar.gz` support
  - proves safety metadata
  - proves incomplete packs fail closed
  - proves markdown includes every required section

## Usage

```bash
PYTHONPATH=. python scripts/guard_runtime_evidence_capture.py runtime/evidence/live_diag_20260522_evidence.tar.gz --today 2026-05-22
```

JSON output:

```bash
PYTHONPATH=. python scripts/guard_runtime_evidence_capture.py runtime/evidence/live_diag_20260522_evidence.tar.gz --today 2026-05-22 --format json --output runtime/evidence/live_diag_20260522_capture_guard.json
```

Gate mode:

```bash
PYTHONPATH=. python scripts/guard_runtime_evidence_capture.py runtime/evidence/live_diag_20260522_evidence.tar.gz --today 2026-05-22 --fail-on-incomplete
```

## Safety

- `broker_api_called=false`
- `is_order_action=false`
- no broker imports
- no order behavior
- no strategy changes
- no dashboard changes
- no threshold loosening
- no live runtime mutation

This PR only reads evidence files and produces a diagnosis report.

## Out of scope

- Quote truth consolidation remains EDGE-42.
- Feed health split-brain correction remains EDGE-43.
- Symbol execution gate remains EDGE-45.
- Strategy validation remains EDGE-52 through EDGE-54.
- Executable quality and paper-truth gates remain EDGE-55 and EDGE-56.
