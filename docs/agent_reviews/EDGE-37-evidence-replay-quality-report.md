# EDGE-37 — Evidence Replay Quality Report

mode: PAPER
candidate_id: EDGE-37
source: docs/agent_reviews/EDGE-37-evidence-replay-quality-report.md
timestamp: 2026-05-22T19:42:00+05:30
decision: add offline/read-only evidence replay reporting for live diagnostic bundles
reason: live diagnostic evidence needs repeatable replay analysis before token, quote-age, fallback, and feed recovery fixes
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

### Scope

Build a repeatable offline report that reads a live diagnostic evidence directory or `.tar.gz` bundle and classifies runtime evidence quality failures.

### Files changed

- `docs/EDGE_TODO.md`
- `core/evidence_replay_report.py`
- `scripts/analyze_live_diag_evidence.py`
- `tests/test_evidence_replay_report.py`
- `docs/agent_reviews/EDGE-37-evidence-replay-quality-report.md`

### Out of scope

- No broker calls.
- No live order behavior.
- No market feed connection changes.
- No strategy rewrite.
- No dashboard changes.
- No token-resolution fix yet.
- No quote-age guard fix yet.
- No fallback firewall yet.

## Grill Me Review

### Hard questions

1. Does this fix expired contracts?
   - No. It detects and reports expired contracts in evidence. EDGE-39 fixes resolution.

2. Does this fix quote-age mismatch?
   - No. It detects mismatch in evidence. EDGE-40 fixes runtime guards.

3. Can this accidentally place orders?
   - No. It only reads local files or extracted tar content and renders JSON/Markdown.

4. Does this prove the strategies are profitable?
   - No. It proves whether evidence is clean enough to reason about executable quality.

5. Does this depend on live market availability?
   - No. It is fully offline and deterministic.

## Hermes Review

### Broker boundary

- `broker_api_called=false`
- `is_order_action=false`
- `live_order_action=false`
- `broker_order_action=false`
- No broker adapters imported.
- No Kite client calls.
- No execution engine calls.

### Runtime boundary

- No `.runtime` mutation.
- No evidence capture loop.
- No log writer usage.
- Report generation reads files and emits stdout or an optional output file only.

## GSD Review

### What this improves

- Converts manual evidence inspection into a repeatable report.
- Detects expired contracts in diagnostic bundles.
- Detects quote timestamp/age mismatch.
- Detects fallback and price-mismatch rows.
- Detects zero executable opportunities.
- Maps evidence-backed issues to observed/not-observed state.

### What this does not improve

- Does not fix token resolution.
- Does not fix feed recovery.
- Does not block fallback execution.
- Does not improve strategies.
- Does not validate profitability.

## Scope Guard

This PR is deliberately report-only. It does not touch production trading path modules such as `core/opportunity_engine.py`, `core/review_queue.py`, `core/entry_semantics.py`, `core/option_token_resolver.py`, or broker execution modules.

## QA / Safety Review

### Tests added

- Synthetic evidence directory report generation.
- Synthetic `.tar.gz` bundle report generation.
- Markdown rendering coverage.
- Missing-file handling without crash.

### Commands to run locally

```bash
pytest tests/test_evidence_replay_report.py -q
python scripts/analyze_live_diag_evidence.py runtime/evidence/live_diag_20260522_evidence.tar.gz --today 2026-05-22
python scripts/analyze_live_diag_evidence.py runtime/evidence/live_diag_20260522_evidence.tar.gz --today 2026-05-22 --format json --output runtime/evidence/live_diag_20260522_report.json
```

## Acceptance Proof

Acceptance requires:

- Focused tests pass.
- CLI can parse a directory source.
- CLI can parse a `.tar.gz` source.
- Missing files are reported, not hidden.
- Report includes evidence map.
- Report is read-only and broker-free.

## Runtime Proof Required After Merge

After merge, run the CLI against the May 22 diagnostic bundle on the local machine:

```bash
python scripts/analyze_live_diag_evidence.py runtime/evidence/live_diag_20260522_evidence.tar.gz --today 2026-05-22
```

Required runtime proof:

- The command completes without broker calls.
- The report classifies expired contract evidence if present.
- The report classifies quote timestamp/age mismatch if present.
- The report classifies fallback/rest/tick-store rows if present.
- The report classifies zero executable opportunities if present.
- The report output is preserved as a local artifact for EDGE-39/40/41 planning.

## What This PR Does Not Prove

This PR does not prove live trading readiness, strategy profitability, broker readiness, order placement safety, feed recovery success, token resolver correctness, fallback firewall correctness, quote timestamp runtime enforcement, dashboard correctness, or paper-trading expectancy.

It only proves that captured evidence can be replayed into a structured report.

## Expected verdict for May 22 diagnostic evidence

The report should classify the diagnostic as not execution-ready if it observes any of:

- expired option contract evidence
- quote timestamp/age mismatch
- fallback/rest/tick-store rows
- price mismatch rows
- unhealthy feed snapshots
- zero executable opportunities

## Human Approval

Human approval required before merge: confirm CI is green and the CLI report is useful against the May 22 evidence bundle on the local machine.


## High-Risk Path Review

N/A
