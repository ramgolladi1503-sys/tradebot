# Profitable Edge Gap Audit

## A. Executive verdict

The repository is not yet a proven profitable edge engine.

It has strong fail-closed safety layers, decent contract separation, and a fairly rich diagnostic surface. What it does not yet have is enough validated edge evidence to justify treating live selections as profitable signal generation rather than conservative filtering.

The current live bottleneck is not a single broken strategy. The bottleneck is a stacked funnel:

1. feed and quote truth is sometimes stale or degraded at the per-symbol option layer,
2. strategy generation is mostly heuristic and regime-shaped, not outcome-proven,
3. scoring is still largely component-weighted heuristic ranking,
4. Phase 2 rejects rows that do not satisfy the execution truth contract,
5. there is still no convincing outcome-linked proof that surviving candidates beat cost and slippage across regimes.

## B. Current system classification

| Dimension | Status | Why |
| --- | --- | --- |
| Infrastructure maturity | Moderate | The repo has clear read-only contracts, runtime evidence writers, and separation between candidate generation, scoring, ranking, and telemetry. |
| Signal quality maturity | Low to moderate | Strategy code exists, but most strategies are regime heuristics with hard thresholds and limited outcome validation. |
| Ranking maturity | Moderate | Ranking is structured and explainable, but it is still mostly heuristic scoring plus safety downgrades. |
| Strategy edge maturity | Low | There is no repository-wide proof that the active strategies have durable positive expectancy after cost. |
| Data truth maturity | Moderate | Feed truth and quote truth are explicitly modeled, but stale/fallback/degraded paths still dominate live blocking. |
| Outcome validation maturity | Low | Outcome contracts exist, but the system is not yet producing enough linked replay/live evidence to prove edge. |

## C. Top 10 blockers to profitable edge

1. Per-symbol option quote freshness is still failing in live runs, so candidates die before selection.
2. Strategies are mostly heuristic regime filters, not validated edge engines.
3. Ranking uses fixed component weights and bucket caps, which is explainable but still not calibrated proof of edge.
4. The live funnel treats stale/fallback/advisory/degraded truth as non-executable, which is correct safety behavior but reduces the chance of proving edge until data quality improves.
5. Outcome contracts exist, but many UI/ranking labels still lack full prediction event, horizon, target, stop, cost, and calibration provenance.
6. Phase 2 is strict enough to reject any row missing execution truth, which is right for safety but means upstream truth gaps look like “no strategies selected.”
7. High-entropy conditions are routed conservatively, and the repo does not yet show a distinct, validated high-entropy strategy family with live proof.
8. Trade-builder rejection reasons are dominated by quote/structure issues such as IV term/slope and stale ticks in the live evidence.
9. There is no convincing per-regime walk-forward evidence proving that the surviving strategies beat cost.
10. Capital allocation and portfolio exposure logic is still secondary to gating, so even valid opportunities are not yet tied to a proven allocation policy.

## D. Top 10 places where trades are blocked before ranking

1. Feed truth / quote truth gating in `core/orchestrator.py`.
2. Trade-builder scan rejection in `strategies/trade_builder.py`.
3. Candidate soft reject augmentation in `core/orchestrator.py::_augment_ranked_candidates_with_soft_reject`.
4. Real vs synthetic candidate split in `core/orchestrator.py`.
5. Executable truth filter in `core/orchestrator.py` via `_candidate_trace_payload`.
6. Regime instability gate in `core/strategy_gatekeeper.py`.
7. Contract-resolution fallback hard block in `core/candidate_finalization.py`.
8. Eligibility contract blockers in `core/strategy_eligibility.py`.
9. Candidate pool blocking in `core/strategy_candidate_pool.py`.
10. No-trade suppression in `core/no_trade_engine.py`.

## E. Top 10 places where bad candidates are correctly blocked

1. `core/candidate_finalization.py` blocks contract-resolution fallback from becoming executable.
2. `core/candidate_ranking.py` suppresses feed-risk candidates via safety tokens.
3. `core/opportunity_scoring.py` penalizes stale option LTP, fallback quote data, wide spread, missing depth, and unresolved contracts.
4. `core/strategy_eligibility.py` blocks missing evidence and regime mismatch.
5. `core/strategy_hypothesis_contracts.py` requires outcome metrics and invalidation structure.
6. `core/strategy_gatekeeper.py` blocks unstable or low-confidence regimes.
7. `core/strategy_candidate_generator.py` rejects unsafe payload shapes.
8. `core/strategy_candidate_pool.py` keeps registry/eligibility invalidity from generating candidates.
9. `core/regime_entropy_gate.py` marks high normalized entropy as uncertain and raises regime risk.
10. `core/ranking_orchestrator`-style downstream wiring keeps advisory rows out of executable buckets when feed truth is degraded.

## F. Top 10 places where bad candidates may still leak

1. Heuristic candidates can still look strong in score terms if the feed-risk tokens are not fully normalized upstream.
2. Some labels such as confidence, probability, and setup score can be read too literally by humans if the UI context is not explicit.
3. The ranking layer still depends on current component weights rather than a verified calibration model.
4. High-entropy gating is conservative, but the repo does not yet show a separately validated high-entropy opportunity class.
5. Strategy descriptions can imply edge more strongly than the replay evidence supports.
6. Outcome contracts are present, but not every candidate path appears to populate them with full calibration provenance.
7. Some live evidence paths still infer or patch data quality instead of treating it as a hard block in every upstream surface.
8. Candidate starvation diagnostics can show candidate counts without proving those rows are actually executable.
9. The system can still emit advisory or no-trade rows that are useful for humans but useless for proving live edge.
10. If the operator reads “ranked” as “profitable,” the current documentation and runtime artifacts are not strong enough to prevent that misunderstanding.

## G. Strategy-by-strategy verdict matrix

| Strategy | File | Market Thesis | Entry Logic | Exit Logic | Regime Dependency | Values / Thresholds | Generic or Evidence-Based? | Needs Backtest? | Needs Live Paper Validation? | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| opening_drive | `strategies/movement/opening_drive.py` | Opening impulse after session start | Session/opening move plus VWAP distance | Pattern-based invalidation | Strong | Fixed thresholds | Generic | Yes | Yes | IMPLEMENTED_BUT_HEURISTIC |
| opening_range_retest | `strategies/movement/opening_range_breakout.py` | Retest of opening range after breakout | ORB retest confirmation | Pattern invalidation | Strong | Fixed thresholds | Generic | Yes | Yes | IMPLEMENTED_BUT_HEURISTIC |
| compression_breakout | `strategies/movement/compression_breakout.py` | Compression resolves into breakout | Compression evidence score | Pattern invalidation | Strong | Fixed thresholds | Generic | Yes | Yes | IMPLEMENTED_BUT_HEURISTIC |
| trend_pullback | `strategies/movement/trend_pullback.py` | Trend continuation after pullback | Trend score + pullback hold | Pullback invalidation | Strong | Fixed thresholds | Generic | Yes | Yes | IMPLEMENTED_BUT_HEURISTIC |
| vwap_reclaim_rejection | `strategies/movement/vwap_reclaim.py` | VWAP reclaim/rejection continuation | VWAP reclaim + confirmation | Reclaim invalidation | Strong | Fixed thresholds | Generic | Yes | Yes | IMPLEMENTED_BUT_HEURISTIC |
| failed_breakout_trap | `strategies/movement/failed_breakout_trap.py` | Failed breakout trap reversals | Trap risk and failed level logic | Trap invalidation | Strong | Fixed thresholds | Generic | Yes | Yes | IMPLEMENTED_BUT_HEURISTIC |
| exhaustion_reversal | `strategies/movement/exhaustion_reversal.py` | Overextension snaps back | Stretch and exhaustion score | Exhaustion invalidation | Strong | Fixed thresholds | Generic | Yes | Yes | IMPLEMENTED_BUT_HEURISTIC |
| mean_reversion_extension | `strategies/movement/mean_reversion_extension.py` | Range extension reverts | Range/chop plus extension distance | Trend continuation filter | Strong | Fixed thresholds | Generic | Yes | Yes | IMPLEMENTED_BUT_HEURISTIC |
| event_volatility_expansion | `strategies/movement/event_volatility_expansion.py` | Event-driven volatility expansion | Event regime and expansion score | Spread/mean-reversion invalidation | Strong | Fixed thresholds | Generic | Yes | Yes | IMPLEMENTED_BUT_HEURISTIC |
| option_pressure | `strategies/movement/option_pressure.py` | Option-side pressure / confirmation | Pressure score with regime context | Pressure invalidation | Moderate | Fixed thresholds | Generic | Yes | Yes | IMPLEMENTED_BUT_HEURISTIC |
| late_day_momentum | `strategies/movement/late_day_momentum.py` | Late-session trend continuation | Late-day timing plus trend | Timing invalidation | Strong | Fixed thresholds | Generic | Yes | Yes | IMPLEMENTED_BUT_HEURISTIC |
| no_trade_chop | `strategies/movement/no_trade_chop.py` | Conservative no-trade in chop | No-trade assessment | N/A | Strong | Fixed thresholds | Safety artifact | No | No | FALLBACK_ARTIFACT |

## H. Ranking/scoring truth matrix

| File | Function/Class | Field | Current Behavior | Problem | Edge Impact | Required Fix Type |
| --- | --- | --- | --- | --- | --- | --- |
| `core/opportunity_scoring.py` | `score_candidate` | `final_score` | Weighted component score minus penalties, capped by bucket | Heuristic, not calibrated to outcomes | Can rank survivors, not prove edge | Backtest calibration + outcome linkage |
| `core/opportunity_scoring.py` | `OpportunityScoreRecord` | `score_eligibility` | Separates eligible / advisory / suppressed / no-trade | Good separation, but still score-centric | Human-friendly but not enough for edge proof | Keep, then calibrate |
| `core/candidate_ranking.py` | `rank_candidates` | `bucket` | Uses hard bucket priority and feed-risk suppression | Ranking still largely order-of-survival after safety filters | Can display the “best remaining” rather than the best opportunity | Add outcome-calibrated ranking model |
| `core/candidate_ranking.py` | `probability_ui_label` | probability label | Shows target-hit label only if outcome contract is explicit | Otherwise falls back to “Setup score” | Avoids some misuse, but not all | UI truth labeling hardening |
| `core/opportunity_scoring.py` | `COMPONENT_WEIGHTS` | component mix | Fixed weights for price structure, confirmation, liquidity, freshness, regime, timing, confluence, volatility | Not evidence-tuned per symbol/regime | Can flatten meaningful differences | Per-regime calibration |
| `core/opportunity_scoring.py` | `DOWNGRADE_REASON_PENALTIES` | penalties | Penalizes stale/fallback/wide-spread/miss-ing-depth/unresolved-contract | Correct safety bias, but still heuristic | Strong safety, weak proof | Keep, then validate against outcomes |

## I. Feed/fallback/stale truth matrix

| Truth Source | Current Behavior | Risk |
| --- | --- | --- |
| Option LTP age | Explicitly evaluated and can block candidates | Good safety, but live freshness gaps are still the dominant blocker |
| Underlying tick age | Used in feed truth / quote truth | If stale or synthetic, live selection degrades quickly |
| Bid/ask spread | Used by scoring and liquidity truth | Good to block expensive entries |
| Depth availability | Used as a downgrade / blocker | Can suppress valid setups when the market is thin |
| Quote source | Classified as real / fallback / synthetic / degraded | Correctly fail-closed when not trustworthy |
| Recovered fallback | Treated as non-executable or advisory in the truth chain | Correct behavior |
| Market session state | Explicitly modeled | Good, but session logic is only as good as upstream truth |
| Websocket connected vs fresh tick truth | Connection alone does not imply selection readiness | Correct separation |

## J. Missing telemetry/artifacts

| Missing Evidence | Required Artifact | Current File / Module | Gap | Priority |
| --- | --- | --- | --- | --- |
| Per-strategy outcome linkage | Replay report by strategy, regime, and symbol | `core/strategy_replay_proof_pack.py` plus replay sources | Not enough live-paper correlation | High |
| Cost-aware validation | MAE/MFE, slippage, target-hit, stop-hit by candidate | `core/candidate_outcome_contract.py` and outcome writers | Contract exists but proof chain is thin | High |
| Live paper acceptance proof | Explicit accept/reject bundle with no missing evidence | paper-trading readiness path | Readiness is conservative but not enough for profitability proof | High |
| Ranking calibration evidence | Outcome-calibrated score table | `core/opportunity_scoring.py` | Scores are still mostly heuristic | High |
| High-entropy design validation | Dedicated entropy regime report | `core/regime_entropy_gate.py` and entropy logs | Entropy blocks are conservative, not yet edge-proven | Medium |
| Top-opportunity selection audit | Candidate-to-top-opportunity lineage report | ranking/orchestrator logs | Hard to distinguish “survived” from “selected for edge” | High |

## K. Missing tests

| Proposed Test Name | Purpose |
| --- | --- |
| `test_live_option_ltp_stale_blocks_executable_candidates` | Prove stale option truth stays non-executable |
| `test_fallback_quote_data_cannot_reach_top_opportunity` | Prove fallback truth cannot rank as executable |
| `test_recovered_fallback_candidates_remain_advisory_only` | Prove recovered data does not revive execution |
| `test_high_entropy_routes_only_approved_strategies` | Prove entropy is routing, not silent relaxation |
| `test_probability_label_requires_outcome_contract_fields` | Prove UI labels only say probability when event/horizon/target/stop/calibration are present |
| `test_rank_bucket_mapping_is_strict_and_non_leaky` | Prove advisory/suppressed/no-trade rows cannot appear as executable buckets |
| `test_candidate_outcome_contract_requires_cost_model_and_calibration` | Force explicit provenance for probability claims |
| `test_live_paper_acceptance_fails_when_no_regime_eligible_strategy_exists` | Prove paper acceptance is fail-closed |
| `test_strategy_candidate_pool_blocks_miss-ing_evidence_contracts` | Prove strategy contract failures stay upstream |
| `test_replay_outcome_linking_by_strategy_and_regime` | Prove future edge claims are linked to actual outcomes |

## L. Recommended PR roadmap

| PR | Title | Goal | Files Likely Affected | Acceptance Criteria | Tests Required | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Observability: candidate lineage and rejection clarity | Make the live funnel explain where candidates die | logs, audit writers, diagnostics | Per-symbol stage counts and reject reasons are explicit | focused diagnostics tests | Low |
| 2 | Safety/truth: tighten truth labeling | Prevent human misread of probability/confidence labels | UI truth labels, outcome contract display paths | No label implies calibrated probability without full contract | label-contract tests | Medium |
| 3 | Strategy correctness: contract and regime audit | Separate heuristic strategy families from evidence-backed ones | strategy registry, eligibility, hypothesis contracts | Every active strategy has an explicit verdict | contract tests | Medium |
| 4 | Ranking/scoring calibration | Replace flat heuristic ranking with outcome-aware calibration | opportunity scoring, ranking reports | Scores correlate to replay outcomes after cost | replay calibration tests | High |
| 5 | Backtest/replay validation | Prove or disprove edge by regime | replay, candidate outcome, walk-forward | Per-regime OOS results are reproducible | replay tests | High |
| 6 | Paper/live soak validation | Validate live candidate behavior under manual approval | paper readiness, acceptance bundles | Acceptance is explicit and fail-closed | soak tests | Medium |
| 7 | UI truth-label cleanup | Keep advisory/watchlist/executable buckets distinct | dashboard/report labels | No advisory row is shown as executable | UI truth tests | Medium |

## Final verdict

The repository is built like a cautious trading system, not yet like a proven edge engine.

The main thing still stopping profitability is not “miss-ing strategies.” It is that the current strategies are still mostly heuristic, the scoring layer is still mostly heuristic, the live data truth chain still blocks many candidates before ranking, and the repo does not yet have enough linked replay/live outcome evidence to prove edge after cost.

The right next move is not to loosen gates. It is to prove which surviving families actually hold up in replay and paper runs, then calibrate ranking from those outcomes.
