# RBFN Exhaustion Gate Reference — Implementation Plan

## Work item and state

- Classification: scoped strategy-gate behavior correction
- Parent Epic: `EPIC-SENTINEL-REGIME-SUPERVISORY` (as referenced by the canonical parent Feature)
- Parent Feature: `FEAT-SENTINEL-STRUCTURAL-GATES-002` (existing Feature record; its old acceptance does not itself accept this behavior change)
- Design candidate: `TRIGGERING_FROZEN_RP1_RP2_BOUNDARY`, selected by the user for each named reversal setup
- Implementation state: `DEV_VERIFIED; QA_PASSED; SENIOR_QA_CODE_REVIEW_PASSED` for the local candidate. Focused module: 83 passed in separate developer, QA, Technical & Quant, and Senior QA runs. Canonical admission/evidence gates remain open; not released or live-authorized.
- Scope of this artifact: approved narrow candidate contract, implementation plan, evidence boundaries
- Safety: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`
- Local audit attachment reviewed: `/Users/madhuram/Downloads/forensic_audit_10_attackers_ce_runner_and_volatility.md` (Nov 19 NIFTY session claims). The three most recent TradeBot conversations were checked; only `162de38c-8263-4254-8b50-0c5fa8538833` covers the Nov 19 live session.

The local patch changes only the exhaustion gate's displacement input for the six enumerated RP1/RP2 reversal/fade reasons and snapshots the triggering boundary on the cached signal. The approved follow-up changes reason text only when a mapped, valid boundary setup is denied specifically by the existing `EXHAUSTED_EXPANSION` reason; the gate boolean, multiplier, ATR, and outer `VOLATILITY_EXHAUSTED` code remain unchanged. It does not change levels, thresholds, ATR source/window, confidence scoring, or other gates. This selected reference is a location heuristic; it does not prove that a particular missed or entered trade was caused by this gate or that outcomes improve.

## User-reported question

The reported concern is that an RBFN reversal near an upper or lower reversal level may be judged against Trend Decider (TD) displacement, so the veto can measure distance from a different reference than the boundary involved in the setup. The user selected the exact frozen RP1/RP2 boundary that generated each named reversal setup as the candidate gate reference, while preserving level values and strategy thresholds. Because this may change which candidates pass the veto, it remains a strategy behavior change and must pass the stated delivery, data, and review gates before it is accepted or promoted.

### Selected candidate contract

- For every explicitly enumerated reversal/fade setup, use absolute spot distance from that setup's exact triggering frozen RP1/RP2 boundary as the exhaustion gate-local displacement.
- Do not infer the boundary from direction alone where the setup name or generator condition identifies another level. Unknown or unmapped setup reasons must fail closed for this candidate path; no silent TD/strike fallback is allowed for a named boundary setup.
- Preserve the existing confidence scorer's TD/fallback `displacement_pts` input; the exhaustion gate gets a separate local value.
- Preserve all level values, the existing 2.5 multiplier, ATR input source/window, strict `>` comparison, other vetoes, and unrelated setup behavior. Keep the confidence scorer's existing TD/fallback displacement unchanged.
- The measured value is `abs(current_spot - triggering_frozen_RP_level)`: a location-to-boundary heuristic. It is not a recent-window displacement, excursion, validated volatility-exhaustion statistic, or profitability measure.
- The triggering boundary must be snapshotted into the frozen cached signal when generated. Do not read a mutable current grid in the later option-depth callback. Missing/non-finite snapshots and unmapped RP1/RP2 reversal/fade names fail closed; unrelated setup families retain their current TD/strike displacement.

## Read-only code and test facts

1. In `core/sentinel_live_stream_advisor.py:4298-4305`, the RBFN path computes `displacement = abs(spot - td_anchor)` when the cached grid has a positive Trend Decider; otherwise it falls back to `abs(spot - rbfn_sig.target_strike)`. The same scalar is sent to the confidence scorer (`:4475-4488`) and to `VolatilityCompressionGate.evaluate_compression` (`:4490-4494`). Therefore a reference-only exhaustion experiment must use a separate gate-local value; it must preserve the existing confidence scorer's `displacement_pts` input unless that additional strategy behavior change is separately authorized. Add a focused assertion that confidence still receives the current TD/fallback displacement.
2. In `core/structural_alpha_gates.py:193-208`, the exhaustion condition is strict: it vetoes only when `abs(recent_displacement_pts) > exhaustion_multiplier * atr_60m`; the default multiplier is 2.5. Equality is not an exhaustion veto under this comparison. The gate also has a separate `atr_60m <= 0` path that returns allowed with `INSUFFICIENT_BASELINE_ATR`; malformed/non-finite input behavior has not been qualified here.
3. RBFN setup generation names and conditions include RP2 lower fast/10-minute floor bounce and RP2 upper fast/10-minute ceiling fade (`core/sentinel_live_stream_advisor.py:3600-3667`), plus RP1 upper/lower reversal setups (`:3748-3788`). These setups use frozen grid RP levels in their conditions, but the later shared RBFN confidence/exhaustion path still receives the TD-based displacement above.

### Corrected producer-to-boundary mapping

The user selected the triggering frozen boundary. Based on the setup names and generator conditions, the candidate mapping is:

| Setup reason | Candidate reference |
|---|---|
| `RP1_UPPER_REVERSAL_CONFIRMED` | frozen `URP1` |
| `RP1_LOWER_REVERSAL_CONFIRMED` | frozen `LRP1` |
| `RP2_UPPER_10M_CEILING_FADE` | frozen `URP2` |
| `RP2_LOWER_10M_FLOOR_BOUNCE` | frozen `LRP2` |
| `RP2_UPPER_FAST_REJECTION` | frozen `URP2` |
| `RP2_LOWER_FAST_BOUNCE` | frozen `LRP2` |

This matches the six exact values in `MODE_5_EXHAUSTION_FADES` and their producers. `RP1_UPPER_10M_EXPANSION_BREAKOUT` and `RP1_LOWER_10M_EXPANSION_BREAKDOWN` are continuation families and remain on the current TD/strike displacement path. Use exact setup-name equality. Unknown RP1/RP2 reversal/fade family names and recognized families with a missing/non-finite boundary fail closed.
4. `tests/unit/test_structural_alpha_gates.py:96-112` tests a 15-point permitted case and a 50-point veto case with ATR60=15; it does not test the exact 2.5× boundary or a just-over boundary.
5. `tests/unit/test_sentinel_adversarial_level_and_strike_audit.py:184-263` asserts that there are zero false SENSEX exhaustion vetoes for its constructed scenario. Its RBFN `setup_reason` is `TD_PULLBACK_REENTRY_BEAR_CONFIRMED_2BAR` (around `:220`), not an RP1/RP2 boundary-reversal setup. It appears to codify the TD reference for that different setup and does not establish that a boundary reversal is measured against its triggering RP level.
6. The identified paths and tests establish implementation behavior and coverage gaps only. They do not prove the intended reference, mathematical superiority of either candidate hypothesis, or impact on today's reported trades.

### Nov 19 local live-artifact cross-check (read-only; incomplete source coverage)

The attached forensic report was compared with the ignored local journal, APM WAL, daily level file, source, and captured market-data manifest. These are local artifacts, not authenticated Anti-gravity answers. Their SHA-256 values at review time were: decision journal `c35a405bcdbdeeb4bf1d39376cb5a972aee8643727d751c56d4c18c9844d1b60`; populated market-data manifest `d28aa79f350f3bfec38391b849f1fc3c38c37e5d83cb94f72a417ae0d1fd290a`. Both files are ignored runtime artifacts and are not added to this planning change.

- `logs/sentinel_decision_journal_20261119.jsonl` contains four NIFTY `EXECUTION` and four matching `EXIT` rows. At 10:25 the entered candidate was `NIFTY 25200 PE` at ₹110.55 under `RP1_UPPER_REVERSAL_CONFIRMED`; a `NIFTY 25500 PE` candidate logged in the same wall-clock second was rejected as `PREMIUM_OVER_CAP` at ₹284.75. This supports the observed premium-cap reason for that alternative contract, but it does not prove both were evaluated in the same decision cycle, identify why the chooser preferred the 25200 strike among all possible candidates, or establish whether another eligible contract was rejected earlier. The other executions were the same `NIFTY 25500 CE` strike at 11:20, 12:08, and 12:24, all under `RP1_UPPER_10M_EXPANSION_BREAKOUT`.
- The local `indices_1m_20261119.parquet` series records NIFTY 50's session low at 25,104.8 at stored timestamp 09:30. Compared with the frozen RP1 lower=25,063 and RP2 lower=25,055, that bar low remained 41.8 and 49.8 points above those levels; the data does not show a touch. The first executed PE was later at 10:25, spot 25,275.5, and is tagged `RP1_UPPER_REVERSAL_CONFIRMED`, not a lower-reversal setup. The decision journal has no earlier NIFTY VETO or EXECUTION rows before 10:25, so available records cannot explain why no PE was entered near the morning low or whether a fast-rejection condition was evaluated. Timestamps in this parquet are timezone-naive and the file has no linked source/rights manifest; treat it as local corroborative context only, not admitted PIT evidence or sub-minute ordering. The parquet's local SHA-256 at review time was `acc199b49b2723747e76d68939bc5b224b8a14abdb8ca7c60db612b4a48ff644`.
- The first CE trade entered at ₹70.10 and exited at ₹84.00 at 12:03:33 with `PEAK_GIVEBACK_CLAMP_EXIT`; the WAL records peak ₹94.70, clamp ₹86.09, one lot, `GEAR_1_RANGE`, non-runner mode, and no half-book. Code (`core/active_position_manager.py:656-704`) computes the clamp from option premium and liquidates the whole position on breach outside trend gear. The later two same-strike trades exited at ₹78.55 (`TRAILING_STOP_HIT`, flat option P&L) and ₹93.50 (`PEAK_GIVEBACK_CLAMP_EXIT`). This proves why those recorded exits fired; it does not prove an alternative exit rule would safely capture the later move.
- The journal contains 109,088 `VOLATILITY_EXHAUSTED` VETO records with unique record IDs across ten CE strikes, all tagged `[MIDDAY_EXPANSION_BREAKOUT] RP1_UPPER_10M_EXPANSION_BREAKOUT`. Their `wall_time_str` values span 11:46:59–14:55 at second precision and cover 10,142 distinct second strings. In the clean isolated source at PR #987 head, `timestamp_ms` is `depth.exchange_timestamp_ms`, and `wall_time_str` is formatted from `now_time`, which derives from that same positive exchange timestamp in `Asia/Kolkata` (`core/sentinel_live_stream_advisor.py:4052-4057`, `:4676-4677`). Comparing all 109,088 rows after interpreting `wall_time_str` as `Asia/Kolkata` yields `timestamp_ms - wall_time_str` in `[0, 0.999]` seconds, consistent with second-precision truncation of the same source timestamp; this does not expose the full-resolution decision instant or prove the exact gate inputs. Per-timestamp candidate counts vary; this is not a count of distinct entry episodes or independent missed trades. The VETO schema omits actual displacement, ATR60, and the gate's compared values, so no exact veto can yet be attributed to reference mismatch from this journal alone.
- `runtime/optionmate_daily_levels.json` records that session's TD=25,185 and RP1 upper=25,305. Veto spots range from 25,347.55 to 25,491.65. Thus an upper-boundary reference mismatch is plausible for this setup family, but the missing per-decision ATR/displacement values prevent calculating which checks would change outcome. Source initializes NIFTY observer ATR at 65, retains up to 20 completed synthetic one-minute high-low ranges, updates observer ATR from their mean, and uses `max(65, observer ATR)` for effective ATR60 (`core/sentinel_live_stream_advisor.py:606-617`, `:1995-2007`, `:3984-4008`). Consequently, the attachment's claim that 65 was necessarily the live ATR for all 109,088 vetoes is unsubstantiated.
- The manifest for the populated capture says `coverage_scope=CURRENT_RUN_ONLY`, `claims_whole_session_complete=false`, 2,090 chunks and 3,563,719 records; its health summary reports `capture_loop_status=ERROR`, `capture_loop_error_type=AttributeError` at 15:25 IST. The captured option stream contains a NIFTY 25500 CE last-traded price (LTP) of ₹153.65 around 15:15 IST; that row records bid ₹152.90 and ask ₹153.25. The LTP exceeds the displayed ask, underscoring that it is not an executable quote. This proves a later recorded LTP in an incomplete run, not a fill or that a hold rule would have survived intervening risks. No P&L or “optimal hold” claim is supported.
- The attachment's “Chebyshev 96%” derivation is mathematically incorrect as written: Chebyshev's inequality gives `P(|X-μ| >= kσ) <= 1/k²`, hence at least 84% within 2.5 standard deviations. ATR is not established here as 1.25 times standard deviation. See [Hebrew University probability notes, Theorem 6.2](https://math.huji.ac.il/~razk/Teaching/LectureNotes/LectureNotesProbability.pdf). Its 5-lot tranche, projected P&L, and drawdown scenarios are hypothetical and do not describe the one-lot live executions. Keep them out of acceptance evidence.

This cross-check improves attribution of recorded execution/veto/exit events but does not select H1/H2, establish a validated edge, or cure incomplete point-in-time data coverage.

## Synthetic counterexamples — illustrative only, not live evidence

These values are deliberately synthetic. Assume an already-confirmed reversal candidate, all other gates permitted, a valid frozen grid, and ATR60=65, giving the unchanged exhaustion limit `2.5 * 65 = 162.5` points.

| Case | Frozen levels and spot | Current TD distance | Candidate boundary distance | Current strict `>` result | Conditional boundary-reference result |
|---|---|---:|---:|---|---|
| Upper RP2 rejection | TD=25,400; RP2 upper=25,700; spot=25,690 | 290 | 10 | 290 > 162.5, veto | 10 is not >162.5, so this gate permits |
| Lower RP2 bounce | TD=25,400; RP2 lower=25,100; spot=25,110 | 290 | 10 | 290 > 162.5, veto | 10 is not >162.5, so this gate permits |

These examples isolate only the reference calculation. They do not establish that such a market/setup occurred, that either candidate would pass the remaining gates, or that an entry would have been executable or profitable.

## Competing, non-equivalent design hypotheses

The user selected H1 as the candidate direction: a frozen per-setup boundary reference. H2 (causal recent displacement) is not selected. This choice is not implementation approval and does not remove the evidence or delivery blockers below.

### H1 — Frozen per-setup boundary reference

For a setup explicitly generated by a frozen boundary, measure candidate displacement relative to the exact boundary that generated it (for example, RP2 upper for an RP2 upper rejection and RP2 lower for an RP2 lower bounce; map RP1 reversal and other families independently). The setup-family-to-reference mapping must be explicit and versioned. Unknown or ambiguous mappings must not silently fall back to TD; they remain `UNKNOWN` and cannot authorize an entry.

**Possible consequence:** a valid rejection close near its triggering boundary can avoid a veto caused by large distance from TD. This may also permit a reversal after a large total-session move even when the local move has not reset; a fixed boundary distance alone does not identify when the current impulse began, whether a pause occurred, or whether volatility has recently expanded.

### H2 — Causal recent displacement from an explicit window or pivot

Measure movement over a predeclared, decision-time-available interval or from a causally identified pivot/reset. The time window, pivot definition, reset behavior, missing-bar behavior, event ordering, and directional semantics must be frozen before replay. No future bar may identify the pivot or complete the window.

**Possible consequence:** this can distinguish a recent burst after a pause from a large accumulated distance since TD. It introduces state and boundary choices that can be unstable across missing/out-of-order bars, session transitions, or alternative pivot definitions. A poorly specified window can create lookahead or selection bias and may allow a genuinely exhausted continuation.

H1 and H2 answer different questions: distance from a structural setup boundary versus magnitude of a recent impulse. Neither should be substituted for the other without a setup-specific product requirement and causal evidence. A hybrid is also a distinct third design and is not implied or approved by this plan.

## ATR input range precondition — source-reviewed for this call path

The ATR path has now been inspected at source level. In `core/sentinel_live_stream_advisor.py:3970-3987`, the option-depth path sets static per-index baseline values: NIFTY `eff_atr_15m=32.5` / `eff_atr_60m=65.0`; BANKNIFTY `45.0` / `65.0`; SENSEX `100.0` / `140.0`. The observer/fallback ATR defaults in that path are NIFTY 65, BANKNIFTY 300, SENSEX 500 (`:3968-3986`); the observer instances are initialized with those values at `:613-617`. Separately, the advisor keeps up to 20 completed synthetic one-minute high-low ranges in `bar_true_ranges` (`:606-612`); on each completed synthetic bar it appends `max(1.0, high-low)`, averages the retained ranges, and updates the observer (`:1995-2003`). The effective values are then `eff_atr_60m=max(static 60m baseline, observer/fallback ATR)` and `eff_atr_15m=max(static 15m baseline, 0.5*eff_atr_60m)` (`:3998-4003`). The separate `index_atr_floors` map used by `clamp_atr` is NIFTY 25, BANKNIFTY 100, SENSEX 150 (`:480-485`, `:1825-1827`); do not conflate it with the defaults above.

`VolatilityCompressionGate.evaluate_compression` itself has permissive behavior for invalid ATR inputs, including NaN, but the inspected `_evaluate_option_depth` path supplies finite positive ATR60 values: fixed positive baseline, observer value selected only when `>0`, observer construction with finite constants, and `update_atr` rejecting non-finite/non-positive updates before assignment. Repository source search found no other production writes to `atr_pts`. This establishes range for this inspected production path, not freshness or statistical quality. The shared gate behavior is not changed here; direct callers remain a separate concern.

## Today's report attribution limit

No per-decision live trace tying each reported setup, frozen grid, spot, ATR values, computed displacement, gate result, other vetoes, and candidate outcome has been supplied in the evidence reviewed for this plan. Therefore today's missed trades cannot be attributed to this exhaustion reference (or ruled out as a cause). A chart showing levels or a later trade outcome is not a substitute for a contemporaneous, joined decision trace. Do not claim that this gate caused, prevented, or would have admitted a reported trade. This missing live trace blocks today's attribution; it is not a requirement to add persistence/telemetry to a reference-only strategy fix. Any new live decision telemetry is a separate work item requiring its own design, scope, and approval.

## Implementation state and acceptance limits

- The user selected the triggering frozen RP1/RP2 boundary and directed implementation of the remaining bugs. No levels or thresholds are changed.
- The existing parent Feature `FEAT-SENTINEL-STRUCTURAL-GATES-002` identifies parent Epic `EPIC-SENTINEL-REGIME-SUPERVISORY`. The Feature is a plausible parent for a supervisory gate fix, but its prior product acceptance does not accept this new behavior. The user's current implementation instruction authorizes this scoped change; it does not certify the existing Feature's old acceptance criteria.
- The repository has no matching Epic/Feature JSON work-item records and parent lock sidecars in `governance/evidence/work_items/`; the supported CLI therefore cannot create a linked bug record yet. No canonical state transition or evidence record is claimed. Platform task-intake integration is also unavailable (`UNSATISFIED`). This patch remains local and unaccepted pending supported work-item admission; this does not invalidate the code-level test results.
- Source review establishes the positive finite ATR range for this call path: the option-depth branch initializes `eff_atr_60m` from finite positive per-index constants; observer ATR is consumed only when positive; observer construction uses finite positive configured defaults; and `update_atr` rejects non-finite or non-positive values before assignment. Source search found no other production assignment to `.atr_pts`. This proves range for the inspected path, not ATR freshness, statistical quality, or PIT source authority.
- Hermes and Grill Me separately reviewed the implementation contract. Their findings require exact six-name mapping, frozen boundary snapshot carried with the signal, preserving old confidence input and unrelated-family behavior, and fail-closed handling for missing/non-finite or unknown candidate references. The location-versus-recent-move limitation is explicit.
- No contemporaneous per-veto trace or licensed PIT replay is available to attribute the Nov 19 session. Do not claim this patch explains a specific veto/trade, improves profitability, or establishes a tradable edge. Those claims remain `UNKNOWN` until evidence exists.
- Code-level development, QA, Technical & Quant review, and Senior QA review are complete. Canonical admission/evidence, exact-head CI, chronological replay, and any promotion or production claims remain open. No live, broker, order, release, merge, or deployment action is authorized by this plan.

No live, paper, broker, order, release, merge, or deployment action is authorized by this plan.

## Acceptance matrix for any later proposal

| Dimension | Required proof before a strategy change can be accepted |
|---|---|
| Setup-family mapping | Test all six exact `MODE_5_EXHAUSTION_FADES` reasons and their frozen boundary fields. RP1 continuation and TD-pullback families retain old displacement. Unknown RP1/RP2 reversal/fade names cannot pass the entry gate; no default-to-TD fallback for the candidate path. |
| Upper/lower symmetry | Mirrored upper and lower fixtures produce directionally symmetric displacement, mapping, gate result, and trace fields; cross-side state or reference leakage is rejected. |
| Exact strict boundary | For frozen threshold `2.5 * ATR60`, prove below and equal do not satisfy the strict `>` exhaustion veto, and just-above does. Preserve the existing operator unless separately authorized. Include positive/negative directional values because current code applies `abs`. |
| Input preconditions | Establish finite-positive ATR range from the inspected option-depth/observer path; separately acknowledge that this does not establish freshness or statistical quality. Unknown reference mappings cannot silently fall back to TD and cannot authorize entry. Do not change ATR source/window or shared invalid-ATR behavior. |
| Reference-only calculation | Use a separate exhaustion-gate input; assert the confidence scorer continues receiving the existing TD/fallback `displacement_pts`. Exercise unchanged other gates and assert that no strategy levels, thresholds, ATR values/source/window, or unrelated veto behavior changed. |
| Decision evidence | Unit/contract tests for the scoped reference calculation must expose the selected reference, computed gate input, strict comparison, and reason sufficiently to verify behavior without adding runtime persistence. A complete live-decision trace is needed for attribution of a specific live trade, but trace completeness/persistence is not part of the reference-only fix. Any new live telemetry is a separate work item/design. |
| Causal replay | Rebuild inputs in event-time order using only information available at each decision. Freeze code/config/data hashes and hypotheses before evaluation; report baseline and each candidate separately, missingness, costs, sensitivity/adverse slices, and `UNKNOWN` outcomes. No post-hoc selection or holdout reuse. |
| Live-day attribution | To claim a cause for a particular missed trade, join it to a contemporaneous setup and complete decision trace. Without this, report cause as unverified; do not infer from a chart or later price path. This is an attribution limitation, not a requirement to build telemetry as part of the reference-only fix. |
| Scope preservation | Verify no RP levels, Trend Decider values, thresholds, ATR source/window, runner behavior, or unrelated veto gates changed without separately reviewed and authorized scope. |

## Review protocol

The user waived the prior ten-attacker/ten-reviewer requirement for now. The repository delivery roles still apply: this implementation received separate Business Analyst, Product Owner, Grill Me, Hermes, GSD, QA, Technical & Quant Analyst, and Senior QA assignments. Those reviews are separately attributed but do not replace canonical delivery admission, product/release approvals, or evidence gates.

## Initial triage role summaries (historical)

The following entries preserve the initial reviews before the user's boundary selection and implementation instruction. Their original blocked/approval-needed statuses are historical and are superseded by the coordinator updates below. They are not current status and do not prove market behavior.

### Business Analyst — separately produced

- **Finding:** When the cached TD anchor is positive, all RBFN setups, including upper/lower reversals, use `abs(spot - TD)`; otherwise the current code falls back to `abs(spot - rbfn_sig.target_strike)`. Setup-specific boundary selection is absent in either branch. A boundary reference is only a candidate hypothesis. Today's live attribution is unproved; parent mapping and admission are unresolved.
- **Evidence:** `core/sentinel_live_stream_advisor.py:4298-4305`, `:3748-3788`.
- **Status:** Requirement clarification needed; implementation blocked.
- **Limit:** No decision-time live trace or approved reference choice was provided.

### Product Owner — separately produced

- **Finding:** The original request supports separate analysis and planning. Changing the reference changes gate outcomes and conflicts with the instruction not to modify strategy; the user must choose/approve the anchor behavior.
- **Evidence:** Current contract and code path at `core/sentinel_live_stream_advisor.py:4298-4305`; no approved reference mapping is recorded in this artifact.
- **Status:** Product approval required before implementation.
- **Limit:** This is a scope/approval finding, not evidence that any missed trade was caused by this gate.

### Grill Me — separately produced

- **Finding:** Named RP2 upper/lower and RP1 upper/lower RBFN reversal/fade setups exist; the wall gate has named exemptions, while the volatility exhaustion check remains unconditional in the shared RBFN evaluation path. The existing SENSEX test asserts zero false exhaustion vetoes for a scenario using `TD_PULLBACK_REENTRY`, not an RP boundary setup. Mirrored synthetic cases can exceed the TD-based threshold while remaining near RP2.
- **Evidence:** `core/sentinel_live_stream_advisor.py:3600-3667`, `:3748-3788`, `:4490-4494`; `tests/unit/test_sentinel_adversarial_level_and_strike_audit.py:184-263`; synthetic values above.
- **Status:** Adversarial design concern; no implementation recommendation authorized.
- **Limit:** Synthetic values are not live evidence. ATR construction is inspected, but source authority/validity and invalid-input behavior need a separately approved contract before changes.

### Hermes — separately produced

- **Finding:** Boundary distance and causal recent displacement are different hypotheses; current evidence cannot select between them. Any choice changes strategy outcomes and requires explicit PO/user approval. ATR source/validity remains separate.
- **Evidence:** Existing TD displacement path and strict gate in `core/sentinel_live_stream_advisor.py:4298-4305`, `:4490-4494`, and `core/structural_alpha_gates.py:193-208`.
- **Status:** `BLOCKED_DESIGN` until one hypothesis has an approved contract and proof plan.
- **Limit:** No live trace or chronological comparison establishes which hypothesis is preferable.

### Technical & Quant Analyst — separately produced

- **Finding:** `abs(spot-TD)` is a distance from a static anchor; by itself it does not measure a recent burst/pause sequence and discards direction. A causal decision-time trace and chronological comparison are required. This is a `CHANGE_REQUIRED` design/evidence finding for any implementation proposal, not proof of today's effect.
- **Evidence:** `core/sentinel_live_stream_advisor.py:4298-4305`; strict gate `core/structural_alpha_gates.py:193-208`; current positive test `tests/unit/test_sentinel_adversarial_level_and_strike_audit.py:184-263`.
- **Status:** `CHANGE_REQUIRED` for a future proposal; unresolved until Hermes contract, trace/replay evidence, and separate analyst closure exist.
- **Limit:** No causal replay or joined live-day trace was available; no quantitative edge claim is made.

### Coordinator update after the separately produced reviews

The user selected the triggering frozen RP1/RP2 boundary and directed implementation. BA and Grill Me found that the original table omitted both RP2 fast families and incorrectly included RP1 continuation families; the corrected six-name table above follows the current `MODE_5_EXHAUSTION_FADES` producer set. Hermes specified capturing the boundary in the immutable cached signal so later grid mutation cannot change it. Grill Me accepted the finite-positive ATR range invariant for this code path; ATR freshness/statistical quality remain unproved. The focused module passed 83 tests in developer, separate QA, Technical & Quant, and Senior QA runs. Technical & Quant's mapping/input findings and reason-label concern were closed by the tested narrow override; Senior QA passed the code/test scope. Canonical admission/evidence, exact-head CI, and market replay remain open. No live attribution or profitability claim is allowed.

### Implementation gate checklist

- [x] Add an optional immutable triggering-boundary field to the cached RBFN signal and populate it at all six setup outputs.
- [x] Use a gate-local distance from the snapshotted boundary only for the six exact fade/reversal reasons; preserve confidence scorer input and unrelated displacement paths.
- [x] Fail closed for missing/non-finite boundary values and unknown RP1/RP2 reversal/fade names; preserve other families.
- [x] Test all six reasons, four RP2 producer variants, both RP1 producers, snapshot across grid replacement, missing/unknown references, scorer preservation, unrelated fallback, and below/equal/above the unchanged 2.5x ATR threshold.
- [x] Gate-input correction: focused test module passed 77 tests in developer and separate QA runs.
- [x] Approved reason-only label clarification: only the mapped veto advisory label changes; 83 focused tests pass and Senior QA passed code/test scope.
- [ ] Resolve canonical linked work-item/evidence admission and exact-head CI. No state transition is fabricated.
- [ ] Keep PIT/causal replay and Nov 19 attribution as open evidence gates; do not treat unit tests as proof of market edge.
