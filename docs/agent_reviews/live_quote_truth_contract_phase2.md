# LIVE Quote Truth Contract → Phase2 Candidate Propagation (Agent Review)

Date: 2026-05-30
Branch: `fix/live-quote-truth-contract-phase2`

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

