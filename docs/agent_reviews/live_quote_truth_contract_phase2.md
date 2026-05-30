# LIVE Quote Truth Contract → Phase2 Candidate Propagation (Agent Review)

Date: 2026-05-30
Branch: `stabilization/tb-edge-candidate-unblock`

## Agent Work Contract

source: agent
mode: stabilization
candidate_id: N/A
decision: add_evidence_and_contract_propagation_only
reason: ensure Phase2 receives real quote-truth fields; fail-closed preserved
timestamp: 2026-05-30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/live_quote_truth_contract_phase2.md

## Scope Guard

- In scope: propagate already-real quote truth fields from option-chain/market-data snapshots into Phase2 candidate inputs.
- Out of scope: broker/order execution, LIVE enablement, ranking/scoring weight tuning, threshold lowering, UI redesign.
- Fail-closed preserved: missing/unknown LIVE truth remains non-executable.

## Grill Me Review

- weak_assumptions:
  - Option-chain rows provide real timestamp + bid/ask for tradable symbols during market open; when missing, Phase2 must block (expected).
  - Cycle timestamp is safe to use only as “now” for deterministic age computation, not as quote timestamp.
- failure_modes:
  - Accidentally defaulting quote truth (age/bid/ask/source) would create unsafe executables in LIVE.
  - Copy-through logic could mask missing top-level fields if it overwrote explicit `None` values incorrectly.
- missing_proof:
  - Market-open live run proof is pending (market closed); evidence artifacts + tests are the current proxy.
- verdict: PASS (evidence-only propagation; strict gates unchanged)

## Architect Review

### Phase2 contract (LIVE)
Phase2 enforces a strict LIVE data contract and will fail-closed when any of the following are missing or unknown:
- `quote_age_sec` (must be derived from a real quote timestamp; never synthesized in LIVE)
- `best_bid` / `best_ask` (real book/quote)
- `spread_pct` (computed only from real bid/ask or carried from upstream real computation)
- `liquidity_score` (must be real or derived from real book where Phase2 already supports it; never invented here)
- `quote_source` must be known (unknown quote source must not become executable in LIVE)

### Quote/depth truth sources
The live option-chain row already contains the truth fields (bid/ask, timestamps, quote source, optional spread/liquidity when computed upstream). The TradeBuilder stamping path is responsible for surfacing these into the candidate/trade object so Phase2 can validate them.

### Minimal patch selected
Smallest safe change: make `TradeBuilder._stamp_quote_truth_snapshot(...)` correctly source truth fields from the option-chain `quote_row` (when present), and derive `quote_age_sec` deterministically from the market-data cycle timestamp *only when* a real `quote_ts_epoch` exists.

## Hermes Review

- scope_pass_fail: PASS
- boundary_violations: none found (no broker/order/live enablement paths touched)
- files_not_to_touch_check: PASS (no credentials/env modifications; no execution boundary edits)
- verdict: PASS

## Safety Auditor Review

### No Phase2 weakening
- No changes to Phase2 hard filters or strict validation logic.
- No changes to scoring/ranking weights or thresholds.

### No fake quote truth in LIVE
- `quote_ts_epoch` is sourced only from explicit quote timestamp fields (`quote_ts_epoch` / `quote_timestamp_epoch`) on trade/source_flags/option-chain row/market-data.
- The market-data cycle timestamp (`timestamp_epoch`) is used only as `now_epoch` for deterministic age computation and is **not** treated as a quote timestamp.
- `spread_pct` is either carried from upstream `spread_pct` or computed from real `best_bid`/`best_ask` plus a real mark/ltp anchor when available. No defaults are introduced in LIVE.
- `liquidity_score` is only propagated when present upstream (trade/source_flags/market_data/option-chain row). No synthetic liquidity is created here.

### Fallback remains non-executable
- No changes that make `fallback` / `recovered_fallback` executable.
- Phase2 adapter change only surfaces already-present truth fields (see below) and does not alter fallback enforcement.

## GSD Review

- purpose: unblock Phase2 strict LIVE contract by propagating real quote truth fields upstream; add tests.
- scope: trade_builder quote truth snapshot stamping + Phase2 dict copy-through; no gate weakening.
- files_changed: `strategies/trade_builder.py`, `core/_engine_phase2_adapter_base.py`, `tests/test_live_quote_truth_contract_phase2.py`, this doc.
- tests_or_reason_not_required: tests added + full suite run (see below).
- evidence: deterministic unit tests prove no fake quote truth is introduced; Phase2 remains strict.
- risks: upstream market-data may omit truth fields during closed market; expected to block. Live validation required when market opens.
- next_pr: none (this is a stabilization base; subsequent clusters are evidence-only).

## QA / Test Review

### Tests added
- `tests/test_live_quote_truth_contract_phase2.py`
  - LIVE: missing quote timestamp → `quote_age_sec` stays `None` and Phase2 fails closed.
  - LIVE: real quote timestamp → `quote_age_sec` deterministically derived from cycle timestamp.
  - LIVE: missing bid/ask → spread context missing and Phase2 fails closed.
  - LIVE: real bid/ask (+ real spread_pct) → spread context populated for Phase2.
  - LIVE strict: unknown quote source hard-fails (via strict drop).

### Why deterministic
Tests supply `market_data["timestamp_epoch"]` to ensure `quote_age_sec` derivation is deterministic and independent of wall-clock time.

## QA / Safety Review

- Confirms:
  - missing LIVE quote truth remains blocked (fail-closed)
  - no fallback/recovered_fallback path is made executable
  - evidence/tests are deterministic and do not depend on wall-clock time

## Files Changed

- `strategies/trade_builder.py`
  - `TradeBuilder._stamp_quote_truth_snapshot(...)`: source truth fields from option-chain row and correct timestamp/age derivation rules.
  - Minimal additional INFO-only evidence log for `NO_CANDIDATE_PATH` when option scan summary is emitted (keeps existing observability expectations).
- `core/_engine_phase2_adapter_base.py`
  - `_candidate_to_dict(...)`: copy-through propagation only (see below).
- `tests/test_live_quote_truth_contract_phase2.py`
  - New deterministic unit/contract coverage for LIVE quote truth propagation into Phase2 inputs.

## Safety Proof: Phase2 Adapter Change

`core/_engine_phase2_adapter_base.py::_candidate_to_dict(...)` only performs **copy-through** from `source_flags.quote_truth_snapshot` (or `source_flags.quote_truth`) into the Phase2 candidate dict when:
- the target field is missing at top-level, and
- the snapshot field is already present upstream.

It does **not**:
- create or default `quote_age_sec`
- create `best_bid` / `best_ask`
- invent `spread_pct`
- default `quote_source` from unknown → real
- modify `_apply_data_fallbacks(...)`
- change fallback execution blocking
- change scoring/ranking weights or thresholds

## Tests Run (Local)

- `PYTHONPATH=. python -m pytest -q tests/test_live_quote_truth_contract_phase2.py`
- `PYTHONPATH=. python -m pytest -q tests -k "phase2 or quote_truth or trade_builder or option_chain or fallback"`
- `PYTHONPATH=. python -m pytest -q tests`

## What Was Not Changed

- Phase2 strictness and hard filters (`_apply_data_fallbacks`, strict drop, hard filters)
- Ranking/scoring weights and thresholds
- Broker/order/execution paths
- Strategy scoring/selection logic beyond quote truth propagation

## High-Risk Path Review

High-risk paths involved (changed or directly impacted):
- `strategies/trade_builder.py` (strategy/candidate construction)
- Phase2 input preparation (`core/_engine_phase2_adapter_base.py`)

Risk posture:
- All changes preserve fail-closed behavior (missing/unknown truth blocks executable output).
- No execution boundary / broker / order action code touched.

## Acceptance Proof

- Deterministic tests show:
  - quote truth fields are propagated when and only when present in upstream real data.
  - missing quote timestamp or bid/ask remains non-executable in LIVE (Phase2 strictness preserved).
  - unknown quote source remains blocked.

## Runtime Proof Required After Merge

- When market opens, capture:
  - `logs/phase2_rejection_latest.json`
  - `logs/feed_truth_latest.json`
  - `logs/top_opportunities_latest.json`
  - confirm real candidates carry quote truth fields and Phase2 rejection outputs align with absent truth (no invented defaults).

## What This PR Does Not Prove

- Does not prove strategy edge/profitability.
- Does not prove market-open executable entries (market closed during stabilization work).
- Does not prove broker reconciliation/execution boundary behavior (intentionally untouched).

## Human Approval

- Required: YES (high-risk area: strategy candidate construction + Phase2 input contract)
- Status: PENDING
