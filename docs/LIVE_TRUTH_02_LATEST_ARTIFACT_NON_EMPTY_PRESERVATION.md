# LIVE-TRUTH-02 — Latest Artifact Non-Empty Preservation

## Purpose

LIVE-TRUTH-02 prevents a useful latest evidence artifact from being erased by an empty runtime cycle.

Target pattern:

```text
previous latest artifact has candidates/opportunities/evidence
next runtime cycle has zero candidates
empty payload overwrites the useful latest artifact
```

## Scope

In scope:

- Detect incoming empty latest-artifact payloads.
- Detect previous non-empty latest-artifact payloads.
- Preserve the previous non-empty payload when the incoming payload is empty.
- Write incoming payloads when they contain useful evidence.
- Emit optional read-only preservation evidence.
- Keep the utility deterministic and atomic through the existing JSON writer.

Out of scope:

- Dashboard changes.
- Candidate generation changes.
- Strategy scoring changes.
- Feed reconnect behavior.
- Runtime snapshot freshness; that belongs to LIVE-TRUTH-03.
- Market-close quiescence; that belongs to LIVE-TRUTH-05.

## Module

```text
core/live_truth_latest_artifact_preservation.py
```

Main functions:

```python
build_latest_artifact_preservation_decision(...)
write_latest_artifact_preserving_non_empty(...)
```

Status values:

- `LATEST_ARTIFACT_INCOMING_WRITTEN`
- `LATEST_ARTIFACT_PREVIOUS_NON_EMPTY_PRESERVED`
- `LATEST_ARTIFACT_PRESERVATION_BLOCKED`

Reason codes:

- `incoming_artifact_non_empty`
- `incoming_artifact_empty_previous_non_empty`
- `incoming_artifact_empty_no_previous_non_empty`
- `invalid_incoming_payload`

## Non-empty definition

A latest artifact is treated as non-empty if it has any useful count, sequence, or signal field.

Examples:

- `source_candidate_count > 0`
- `ranked_executable_count > 0`
- `top_opportunities` contains rows
- `rows` contains rows
- `top_reportable_executable=true`
- `top_executable_trace` is present

## Boundaries

This PR is a preservation utility only. It does not add generation, scoring, feed, runtime-state, or UI behavior.

## Test proof

Focused tests cover preservation, valid overwrite, empty-first write, invalid input blocking, non-empty detection, file-level write behavior, serialization, and read-only/no-append flags.

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_live_truth_02_latest_artifact_preservation.py
```

## Next

After LIVE-TRUTH-02 merges green, continue to LIVE-TRUTH-03 — Runtime Snapshot Freshness Guard.
