# PR #937 — CAS Subprocess Token Binding Repair and Non-Colliding Live Observation Restarts

mode: PAPER
candidate_id: PR937_CAS_SUBPROCESS_TOKEN_BINDING_REPAIR
decision: REVIEW_PASS_READ_ONLY_REPAIR
reason: Pure underlying token resolution across subprocess boundary and non-colliding session start timestamp proven with 20 passing unit tests.
timestamp: 2026-09-28T20:00:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr937_cas_subprocess_token_binding_repair.md

**PR**: #937
**Branch**: `fix/cas-subprocess-token-binding-repair-v1`
**Base Main**: `0f95e60335ddcadbe397e5ca837946ed8b1cdec7`
**Merge Base**: `0f95e60335ddcadbe397e5ca837946ed8b1cdec7`
**Predecessor Live Producer**: `f7b32fcd6302ad4ac6a7b2ff20e63299686a0156`

---

## Agent Work Contract

### Scope
- Extract pure `resolve_cas_underlying_token` function into `core/kite_read_only_observation_runtime.py` to resolve NIFTY token from launch plan `production_resolution` and feed binding map across the subprocess boundary.
- Wire `resolve_cas_underlying_token` into `run_observation` in place of inline resolution logic.
- Replace test-local resolution duplication in `tests/test_candidate_pipeline_architecture_repair.py` with comprehensive unit tests for `resolve_cas_underlying_token` testing positive resolution, precedence, absent dictionary entries, malformed/non-integral inputs, conflicting tokens, and disjoint binding maps.
- Prove non-colliding session start semantics in `scripts/run_market_event_graph_live_session_v1.py` and add unit tests in `tests/test_run_market_event_graph_live_session_v1.py`.

### Non-Goals
- No placement, modification, or cancellation of orders (`is_order_action=false`).
- No broker write calls or credential modifications (`broker_api_called=false`, `broker_write_authority=false`).
- No live or paper execution enablement (`live_authorized=false`, `paper_authorized=false`).
- No weakening of risk gates, feed freshness checks, or kill switches.

---

## Scope Guard

### Allowed Files (PR Scope)
- `core/kite_read_only_observation_runtime.py`
- `scripts/run_market_event_graph_live_session_v1.py`
- `tests/test_candidate_pipeline_architecture_repair.py`
- `tests/test_run_market_event_graph_live_session_v1.py`
- `docs/agent_reviews/pr937_cas_subprocess_token_binding_repair.md`

### Protected Boundaries Untouched
- `core/broker/`, `core/execution/`, `core/order/`, and live trading runbooks remain untouched.
- `config/` and credentials remain completely unmodified.
- `ReleaseStore` journal and historical instrument authorities are not modified by this review.

---

## Grill Me Review

**Challenge 1**: Does `resolve_cas_underlying_token` execute real production code or just test helpers?
**Defense**: The function `resolve_cas_underlying_token` is defined as a pure, exported function in `core/kite_read_only_observation_runtime.py` (lines 137–204) and is directly called by `run_observation` (line 522). Unit tests in `tests/test_candidate_pipeline_architecture_repair.py` import and execute this production function directly.

**Challenge 2**: Does the September 28, 2026 live session certify successor commit `e1554c531`?
**Defense**: No. The September 28 live session ran between ~15:00 and 15:45:01 IST under predecessor SHA `f7b32fcd6302ad4ac6a7b2ff20e63299686a0156`. Successor candidate `e1554c531` was created post-market-close and has `SUCCESSOR_LIVE_EVIDENCE: NOT_PERFORMED`.

**Challenge 3**: Does passing unit tests permit merging PR #937?
**Defense**: No. Merging PR #937 is blocked (`PR_MERGE_GATE: BLOCKED`) until required remote CI workflows pass, successor live market observation is verified, and ReleaseStore provenance is reconciled.

---

## Hermes Review

**Architecture Alignment**:
- Architectural separation between launch plan resolution, live observation runtime, and strategy shadow adapters is preserved.
- Pure resolver function pattern ensures no side-effects or implicit environment dependencies.
- Subprocess boundary passes authoritative token cleanly from preflight launch plan into `CASPrimitiveStore`.

---

## GSD Review

**Execution Verification**:
- Pure function extracted and wired in `core/kite_read_only_observation_runtime.py`.
- Unit tests written and verified for all edge cases in `tests/test_candidate_pipeline_architecture_repair.py`.
- Collision tests added and passing in `tests/test_run_market_event_graph_live_session_v1.py`.
- EOF trailing blank lines removed from both test files, restoring clean `git diff --check`.

---

## QA / Safety Review

**Safety Invariants Verified**:
```text
read_only = true
order_authority = false
broker_write_authority = false
broker_api_called = false
ORDERS_PLACED = 0
ORDERS_MODIFIED = 0
ORDERS_CANCELLED = 0
```
- Predecessor 2026-09-28 live session verified: exactly 2,530 pulses across `native_pulse_stream.jsonl`, `trade_truth_stream.jsonl`, and `strategy_observations.jsonl`.
- Unbroken parent hash lineage: 0 breaks in pulse chain.
- Shutdown drain: graceful exit with `PARTIAL` drain seal at 15:45:01 IST.

---

## Acceptance Proof

**Offline Unit Tests**:
```bash
pytest -q tests/test_candidate_pipeline_architecture_repair.py tests/test_run_market_event_graph_live_session_v1.py
```
- Results: 20 passed (15 in repair suite, 5 in orchestrator suite).

**Git Diff Whitespace Check**:
```bash
git diff --check 0f95e60335ddcadbe397e5ca837946ed8b1cdec7
```
- Results: Clean (no trailing whitespace or blank lines at EOF).

---

## Runtime Proof Required After Merge

Before enabling live observation under candidate SHA:
1. Conduct prospective read-only observation run during active market hours (09:15–15:30 IST).
2. Verify prospective capture of 09:15 and 10:00 CAS primitives with `capture_status: "PASS"` and valid exchange timestamps.
3. Validate unbroken ledger lineage and clean shutdown drain (`final_seal: "PASS"`).

---

## What This PR Does Not Prove

- This PR does **not** prove directional trading edge or strategy alpha profitability (`STRUCTURAL_EDGE: NO_CERTIFIED_EDGE`).
- This PR does **not** certify successor candidate `e1554c531` for live production trading without prospective market execution.
- This PR does **not** repair upstream CI workflow baseline drift in PR782 or Repo Forensics gates.

---

## Human Approval

- **Owner Guidance**: Scoped decision authorization for Items 1–3 issued on 2026-09-28 for EOF whitespace cleanup and truthful agent review documentation.
- **Merge Status**: PR #937 remains **BLOCKED** from merging. No authority is granted or claimed to merge PR #937 to `main`.
