# PR-OBS-15A — Legacy Evidence Import Agent Evidence

```yaml
mode: paper_review
timestamp: 2026-05-23T09:05:00Z
candidate_id: pr_obs_15a_legacy_evidence_import
decision: approve_scoped_legacy_import
reason: partial_legacy_evidence_to_replayable_jsonl
is_order_action: false
broker_api_called: false
source: docs/observability/LEGACY_EVIDENCE_IMPORT.md
```

## Agent Work Contract

Build a scoped legacy evidence importer for old preserved logs and UI snapshots only.

Files in scope:

```text
scripts/import_legacy_observability.py
tests/test_import_legacy_observability.py
docs/observability/LEGACY_EVIDENCE_IMPORT.md
docs/agent_reviews/pr_obs_15a_legacy_evidence_import.md
```

## Scope Guard

Allowed:

```text
Read old CSV, JSONL, or text evidence.
Convert rows into observability JSONL.
Generate missing identifiers deterministically.
Mark converted rows as inferred partial evidence.
Validate output through existing observability event validation.
Allow replay_trace.py to inspect converted rows.
```

Not allowed:

```text
Runtime startup.
State writes outside requested output file.
Strategy changes.
Ranking changes.
Risk changes.
Dashboard changes.
External integration changes.
Claims that old rows are complete traces.
```

## Grill Me Review

Risk: imported rows could be mistaken for full telemetry.
Mitigation: every row includes legacy_import, inferred, and replay_quality markers.

Risk: generated identifiers could be unstable.
Mitigation: identifiers use batch ID, row index, and deterministic row hashes.

Risk: malformed output could break replay.
Mitigation: output is validated through the existing observability event validator before writing.

## Hermes Review

The importer is deterministic, local, and reviewable. It preserves the boundary between historical evidence and real runtime observability.

## GSD Review

This PR lets closed-market historical evidence become replayable without overstating what old logs can prove.

## QA / Safety Review

Coverage:

```text
CSV import.
JSONL import.
Text key-value import.
Existing ID preservation.
Generated ID creation.
Replay compatibility.
Partial evidence markers.
Empty input failure.
CLI output path.
```

## Acceptance Proof

Command:

```bash
python -m pytest tests/test_import_legacy_observability.py
```

Required proof:

```text
Imported rows validate as observability events.
Converted rows can be replayed by replay_trace.py.
Converted rows remain clearly marked as partial legacy evidence.
```

## Runtime Proof Required After Merge

Run the importer against one preserved real log or UI snapshot file, then replay one converted candidate using scripts/replay_trace.py.

## What This PR Does Not Prove

This PR does not prove strategy quality, profitability, complete historical lineage, or correctness of missing fields that did not exist in old logs.

## Human Approval

Ready for PR review after CI passes.


## High-Risk Path Review

N/A
