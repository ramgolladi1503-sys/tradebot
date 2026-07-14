IMPLEMENTATION DIRECTION:
RIGHT

APPROVED OBJECTIVE:
Complete semantic candidate-versus-Phase-2 ownership without changing setup definitions, setup evidence or thresholds.

WHAT WAS ACTUALLY IMPLEMENTED:
Raw directional candidates now describe setup thesis only. Phase-2 option/liquidity/freshness semantics were removed from raw `entry_trigger`, `invalid_if`, `rank_reason`, and raw confluence tags across the affected movement generators. No setup formulas, thresholds, context propagation, or downstream enrichment math changed. A new focused semantic-ownership test suite proves the wording cleanup, exact score-ownership arithmetic, and that Phase-2 eligibility still does not bypass manual approval or risk gating.

ARCHITECTURE CHANGE:
NONE

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

STARTING COMMIT:
`a3abb328229e87ee2587678c41f4d60bce1a4a33`

PHASE 0 COMMIT:
`cf2d74bc7a2938a08bc651e25b5334481479d68c`

PHASE 1A COMMIT:
`9ace90c0b49d790f0e8926a75ecd9492ae6d3b26`

PHASE 1B COMMIT:
`2a247ec6d92f60aa101d462eb6f3013d1aec4d54`

PHASE 1C COMMIT:
`e74bbac98cfb3db43e15129bc78be4bb47564c45`

PHASE 2A COMMIT:
`db19774008db93671c8a24b93f98cb7488498ad2`

PHASE 2B COMMIT:
`b9142aa04cb977eea9eb9eff0eb6d6a2893c1d85`

PHASE 2B OBSERVABILITY COMMIT:
`2262e3baecb05b43f6113989f9715ea3ff199433`

FILES CHANGED:
- `strategies/movement/opening_drive.py`
- `strategies/movement/opening_range_breakout.py`
- `strategies/movement/compression_breakout.py`
- `strategies/movement/trend_pullback.py`
- `strategies/movement/vwap_reclaim.py`
- `strategies/movement/failed_breakout_trap.py`
- `strategies/movement/exhaustion_reversal.py`
- `strategies/movement/mean_reversion_extension.py`
- `strategies/movement/event_volatility_expansion.py`
- `strategies/movement/late_day_momentum.py`
- `tests/test_candidate_phase2_ownership.py`
- `tests/test_candidate_phase2_semantic_ownership.py`
- `docs/agent_reviews/strategy_truth_phase2c_candidate_phase2_ownership.md`

RAW SEMANTIC OWNERSHIP AUDIT:
- Raw candidate text now stays within setup-thesis scope only.
- Removed from raw semantics: `option_confirmation`, `option-side confirmation`, `option_quote_degrades`, `tradable`, `freshness`, `liquidity`, `validated`, and execution-approval language.
- Downstream option confirmation remains represented only in `CandidateOptionConfirmation`, enriched candidate fields, and enriched evidence payloads such as `option_confirmation_truth`, `liquidity_truth`, and `freshness_truth`.
- Raw evidence still carries observed market fields like `option_ltp`, `premium_change`, `spread_pct`, and `depth`, but not as truth-claim keys such as `option_confirmation_truth` or `execution_eligible`.

BEFORE/AFTER RAW THESIS STRINGS:
- `opening_range_retest_v1`
  - Before: `opening_range_breakout_retest_hold_with_option_confirmation`
  - After: `opening_range_breakout_retest_hold`
  - Before reason: `opening range breakout retest held with option-side confirmation`
  - After reason: `opening range breakout retest held`
- `compression_breakout_v1`
  - Before: `compression_range_breakout_with_option_premium_expansion`
  - After: `compression_range_breakout_release`
  - Before reason: `range and ATR compression released into a confirmed option-side breakout`
  - After reason: `range and ATR compression released into a directional breakout`
- `trend_pullback_v1`
  - Before: `trend_pullback_hold_with_option_premium_resumption`
  - After: `trend_pullback_hold_resume`
  - Before reason: `established trend resumed after controlled pullback with option-side confirmation`
  - After reason: `established trend resumed after a controlled pullback`
- `opening_drive_v1`
  - Before: `opening_drive_with_vwap_alignment_and_option_confirmation`
  - After: `opening_drive_with_vwap_alignment`
- `vwap_reclaim_rejection_v1`
  - Before: `confirmed_vwap_reclaim_or_rejection_with_option_confirmation`
  - After: `confirmed_vwap_reclaim_or_rejection`
- `failed_breakout_trap_v1`
  - Before: `failed_breakout_reentry_with_opposite_option_confirmation`
  - After: `failed_breakout_reentry`
- `exhaustion_reversal_v1`
  - Before: `stretched_move_premium_stall_with_opposite_option_confirmation`
  - After: `stretched_move_exhaustion_stall`
- `mean_reversion_extension_v1`
  - Before: `range_extension_with_opposite_option_confirmation`
  - After: `range_extension_reversion_setup`
- `event_volatility_expansion_v1`
  - Before: `volatility_expansion_with_directional_price_and_option_confirmation`
  - After: `volatility_expansion_with_directional_price`
- `late_day_momentum_v1`
  - Before: `late_day_directional_continuation_with_option_confirmation`
  - After: `late_day_directional_continuation`

ENTRY-TRIGGER AND INVALIDATION AUDIT:
- Opening-range, compression, trend-pullback, VWAP reclaim, failed-breakout, exhaustion, mean-reversion, opening-drive, event-volatility, and late-day generators all dropped `option_quote_degrades` from raw `invalid_if`.
- Raw invalidation text is now setup-owned only:
  - `opening_range_retest_v1`: `price_returns_inside_opening_range`
  - `compression_breakout_v1`: `price_returns_inside_compression_range`
  - `trend_pullback_v1`: `pullback_breaks_anchor`
  - `opening_drive_v1`: `price_reclaims_opening_drive`
  - `vwap_reclaim_rejection_v1`: `price_crosses_back_through_vwap`
  - `failed_breakout_trap_v1`: `price_rebreaks_failed_level`
  - `exhaustion_reversal_v1`: `trend_continuation_reaccelerates`
  - `mean_reversion_extension_v1`: `extension_expands_into_trend_continuation`
  - `event_volatility_expansion_v1`: `price_mean_reverts_against_expansion`
  - `late_day_momentum_v1`: `momentum_fades_or_price_returns_to_vwap`

RAW CONFLUENCE-TAG AUDIT:
- Removed `option_confirmation` from raw tags in:
  - `opening_drive_v1`
  - `opening_range_retest_v1`
  - `compression_breakout_v1`
  - `trend_pullback_v1`
  - `vwap_reclaim_rejection_v1`
  - `mean_reversion_extension_v1`
  - `event_volatility_expansion_v1`
  - `late_day_momentum_v1`
- Removed `opposite_option_confirmation` from raw tags in:
  - `failed_breakout_trap_v1`
  - `exhaustion_reversal_v1`

SCORE DECOMPOSITION MATRIX:

`opening_range_retest_v1`
- Pre-Phase2C mixed raw score: `0.639513`
- Post-Phase2C setup score: `0.328053`
- Legacy weighted setup slice: `0.191513`
- Legacy weighted downstream slice removed: `0.448000`
- Arithmetic delta: `0.311460`
- Exact components:
  - `0.25 * price_structure_score = 0.082013`
  - `0.25 * option_confirmation_score = 0.150000`
  - `0.20 * liquidity_score = 0.172000`
  - `0.15 * freshness_score = 0.126000`
  - `0.15 * regime_alignment_score = 0.109500`

`compression_breakout_v1`
- Pre-Phase2C mixed raw score: `0.675169`
- Post-Phase2C setup score: `0.470676`
- Legacy weighted setup slice: `0.227169`
- Legacy weighted downstream slice removed: `0.448000`
- Arithmetic delta: `0.204493`
- Exact components:
  - `0.25 * price_structure_score = 0.117669`
  - `0.25 * option_confirmation_score = 0.150000`
  - `0.20 * liquidity_score = 0.172000`
  - `0.15 * freshness_score = 0.126000`
  - `0.15 * regime_alignment_score = 0.109500`

`trend_pullback_v1`
- Pre-Phase2C mixed raw score: `0.719646`
- Post-Phase2C setup score: `0.648584`
- Legacy weighted setup slice: `0.271646`
- Legacy weighted downstream slice removed: `0.448000`
- Arithmetic delta: `0.071062`
- Exact components:
  - `0.25 * price_structure_score = 0.162146`
  - `0.25 * option_confirmation_score = 0.150000`
  - `0.20 * liquidity_score = 0.172000`
  - `0.15 * freshness_score = 0.126000`
  - `0.15 * regime_alignment_score = 0.109500`

EXACT ARITHMETIC RECONCILIATION:
- Legacy mixed raw-score formula from pre-Phase2C `make_candidate()`:
  - `0.25 * price_structure_score`
  - `+ 0.25 * option_confirmation_score`
  - `+ 0.20 * liquidity_score`
  - `+ 0.15 * freshness_score`
  - `+ 0.15 * regime_alignment_score`
- Current raw-score formula:
  - `raw_score = price_structure_score`
- Proof:
  - The setup-specific `price_structure_score` values for ORB, compression, and trend pullback remain exactly `0.328053`, `0.470676`, and `0.648584`.
  - The prior mixed raw scores reconcile exactly to the weighted components above.
  - The current raw score is the unchanged setup-owned calculation only; no generator threshold or setup-formula threshold changed in this corrective patch.

PHASE-2 ELIGIBILITY DEFINITION:
- `StrategyCandidate.executable_eligible` at `core/movement_contract.py:369-370` means only:
  - candidate status is `VALIDATED_CANDIDATE` or `RANKED_OPPORTUNITY`
  - and candidate has no hard blocker
- This is a Phase-2/pipeline readiness signal, not order authorization.

ELIGIBILITY WRITERS AND READERS:
- Writer of raw readiness state:
  - `strategies/movement/_utils.py::make_candidate()` writes `RAW_CANDIDATE`
- Writer of enriched readiness state:
  - `core/option_confirmation.py:225-266` upgrades directional candidates to `VALIDATED_CANDIDATE` or `BLOCKED_CANDIDATE` and writes real `option_confirmation_score`, `liquidity_score`, and `freshness_score`
- Report readers:
  - `core/candidate_pool_orchestrator.py:176-198` counts `candidate.executable_eligible` for reporting and suppression only
  - `core/candidate_classifier.py` buckets candidates into `EXECUTABLE_CANDIDATE`, `NEAR_EXECUTABLE_CANDIDATE`, or advisory/suppressed classes without placing orders
- Execution/tradability readers:
  - `strategies/trade_builder.py:1357-1388` requires `execution_allowed`, `tradable`, executable entry truth, quote freshness, liquidity, and spread validation before returning `EXECUTABLE`
  - `strategies/trade_builder.py:5489-5499` derives final `execution_allowed_final` only after nonlive executable truth and hard-blocker checks

MANUAL-APPROVAL BOUNDARY PROOF:
- `core/execution_guard.py:56-76` shows manual approval is a separate gate via `must_have_valid_approval(...)`.
- New focused test proves a Phase-2-eligible candidate still fails with:
  - `manual_approval_required:...`
- Result:
  - `candidate.executable_eligible=True` does not bypass manual approval.

RISK-BOUNDARY PROOF:
- `core/execution_guard.py:293-302` explicitly calls `risk_state.approve(trade)`.
- New focused test injects a rejecting `risk_state` and proves the result is:
  - `allowed=False`
  - `reason="RiskState: risk_blocked_for_test"`
- Result:
  - Phase-2 eligibility does not bypass risk approval.

DOWNSTREAM CONFIRMATION ARTIFACT PROOF:
- `core/option_confirmation.py:239-265` still enriches candidates with:
  - `option_confirmation_truth`
  - `liquidity_truth`
  - `freshness_truth`
- New focused test proves enriched directional candidates retain:
  - `option_confirmation_score=0.81475`
  - `liquidity_score=0.86`
  - `freshness_score=0.84`
- Raw `rank_reason` strings no longer mention option confirmation, while downstream truth remains visible in enriched evidence and `CandidateOptionConfirmation`.

EXECUTION-AUTHORITY TRACE RESULT:
- No evidence found that `candidate.executable_eligible=True` alone authorizes an order.
- Actual order/execution authority remains downstream:
  - manual approval
  - trade-builder execution truth
  - `tradable`
  - `execution_allowed`
  - execution guard
  - survival gates
  - risk approval

NO-TRADE VERIFICATION:
- `NO_TRADE_CHOP` remains `safety_suppression`.
- Canonical runtime identity remains `no_trade_engine_v1`.
- No no-trade threshold or role changes were made in this corrective patch.

EXPECTED OWNERSHIP CORRECTIONS:
- Raw candidate wording changed from Phase-2-confirmed semantics to setup-thesis semantics.
- Raw confluence tags no longer claim downstream option confirmation.
- Downstream confirmation remains present only after enrichment.

UNEXPECTED SETUP CHANGES:
- None observed.

FOCUSED TEST COMMAND AND RESULT:
```bash
python -m pytest -q \
  tests/test_candidate_phase2_semantic_ownership.py \
  tests/test_candidate_phase2_ownership.py \
  tests/test_strategy_missing_evidence_observability.py \
  tests/test_strategy_missing_evidence_policy.py \
  tests/test_strategy_context_truth.py \
  tests/test_strategy_profile_fail_closed.py \
  tests/test_candidate_pool.py \
  tests/test_candidate_pool_orchestrator.py \
  tests/test_option_confirmation.py \
  tests/test_no_trade_engine.py
```
- Result: `108 passed, 1 warning in 39.22s`

DISCOVERED OWNERSHIP/APPROVAL TEST COMMAND AND RESULT:
```bash
python -m pytest -q $(rg -l "execution_eligible|manual_approval|risk_approved|RAW_CANDIDATE|CandidateOptionConfirmation|option-side confirmation|confirmed option-side" tests --glob 'test*.py' | sort)
```
- Result: `463 passed, 1 warning in 51.58s`

STATIC CHECKS:
```bash
python -m py_compile strategies/movement/*.py tests/test_candidate_phase2_semantic_ownership.py
ruff check strategies/movement tests/test_candidate_phase2_semantic_ownership.py
git diff --check
```
- Result: all passed

FULL-SUITE RESULT:
- `1 failed, 5726 passed, 1 deselected, 935 warnings in 310.55s (0:05:10)`

FIRST FAILURE:
- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- Failure remained on the established auth baseline:
  - `RuntimeError:[AUTH] missing_kite_access_token`
  - `Missing token at /Users/madhuram/tradebot-strategy-truth-foundation/.runtime/kite_access_token`
  - `Run scripts/kite_autologin_localhost.py to refresh token.`

BEHAVIOR PRESERVED:
- Setup formulas unchanged
- Setup thresholds unchanged
- Strategy IDs unchanged
- Directions unchanged
- Raw setup scores unchanged from current Phase 2C structural ownership behavior
- Phase 1C fail-closed profile behavior unchanged
- Phase 2A truthful StrategyContext propagation unchanged
- Phase 2B missing-evidence policy unchanged
- Phase 2B blocker observability unchanged
- No broker, network, execution, or persistent-thread activity introduced

RISKS:
- Raw evidence payloads still contain option-market observations such as `option_ltp`, `premium_change`, `spread_pct`, and `depth`; they are observational, not truth-claim fields, but external consumers that treat any option fields as downstream confirmation could still misread them.
- Legacy consumers comparing current raw scores to pre-Phase2C mixed scores may misinterpret the semantic score change if they ignore the ownership decomposition above.

ROLLBACK:
- Revert only the semantic-ownership corrective commit once created.
- Do not revert Phase 2C structural ownership, Phase 2B missing-evidence safety, or Phase 2A truthful context propagation.

EXPLICIT NON-CLAIMS:
- This patch does not add temporal completed-bar history.
- This patch does not change setup definitions, thresholds, ranking formulas, no-trade policy, risk policy, manual-approval policy, broker behavior, or execution behavior.
- This patch does not claim trading edge, better profitability, or higher candidate quality.
