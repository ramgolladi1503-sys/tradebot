# PR #992 OptionMate Reconstruction Audit

**Audit date:** 2026-11-02
**Audited PR head:** `a626a3eaa6a9c6e3d5fccb5f192ca25b65daad6f`
**PR state:** OPEN
**Merge state:** BEHIND
**Verdict:** `NO-GO / RESEARCH-ONLY / NOT_MEASURABLE`

This audit describes PR #992's code and result artifacts and compares them with timestamped paraphrases from Telugu captions and English auto-captions, including direct playback reviewed 2026-11-03. Translation/caption rendering may be inaccurate and provenance/authorship is unspecified. Raw transcript exports are temporary and not included; their hashes and evidence limits are recorded in [`OPTIONMATE_TRANSCRIPT_EVIDENCE_REGISTER_20261102.md`](OPTIONMATE_TRANSCRIPT_EVIDENCE_REGISTER_20261102.md). The audit does not establish that PR #992 reproduces OptionMate's proprietary model, decisions, or results. PR #992 has not been modified or commented on.

## PR scope snapshot

The GitHub PR diff snapshot reports base `main` at `6de80a39c7d0deb4cafe718ec4cd44dade260afa`, PR head `a626a3eaa6a9c6e3d5fccb5f192ca25b65daad6f`, 116 changed files, and +107,655/−85 lines.

The head commit's own stat is a different comparison: 35 files changed, +6,549 lines. Exact-SHA CI `changed_paths` counts use other comparison bases: `code-excellence-base-authority` reported 127; `code-excellence-gates` reported 116. These figures are not interchangeable.

Representative files in the GitHub PR diff outside the RBFN research area include:

- `core/sentinel_live_stream_advisor.py`
- `core/active_position_manager.py`
- `core/upstox_stream_broadcaster.py`
- `scripts/upstox_daily_live_capture_and_stitch.py`
- `scripts/trading_schedule_daemon.py`

The PR is over-scoped and includes runtime-facing paths alongside research work. Their presence alone does not establish that these files enable LIVE orders.

The `pr818-live-flow-freeze-target` check failed with `PR818_FROZEN_LIVE_FLOW_VIOLATION`, naming `core/kite_depth_ws.py` against frozen SHA `d7dc45e7c5c76247e7d1b8abd40ec7682fac2f9b`. That path is not in GitHub's PR file list; this finding is not a claim that `core/kite_depth_ws.py` appears in the direct PR diff.

## Recording evidence and boundaries

The timestamp register contains paraphrases from English translated auto-captions. Caption wording around 4:31 (“four prices” and “five”) is ambiguous. At 4:40, direct playback shows a NIFTY 50 Index chart with “Reversal Price” and “Trend Decider Price” overlays; the screenshot was not committed and can be rechecked at that timestamp. This supports chart/spot classification, but not an exact overlay count or formula. Later captions separately support narrow discussion of option-chain values 38 and 68, an unclear third price, and selecting a strike. The unqualified “138” at 6:11 has unresolved meaning/unit/relation. No evidence connects the early chart overlays, the later premium examples, or an RBFN output to the user's clarified ₹28/₹38/₹68/₹128/₹158 values. The captions do not disclose the model inputs, RBFN architecture/training, deterministic strike mapping, or complete entry/exit logic. Approximate stops and time-of-day comments remain translation-dependent discretionary examples, not fixed rules.

The user clarified that ₹28/₹38/₹68/₹128/₹158 are RBFN-derived option-premium values followed by nearby-strike selection. This is `USER_CLARIFICATION`, not source-verified, and these values are not strike identifiers or established chart-level prices. Captions around 55:27/55:39/56:08 narrowly mention 38 and 68 in option-chain context and selecting a strike, with a third price unclear. The unqualified 138 at 6:11 has unresolved meaning, unit/currency, and relation to any other value; no supported link to the user's clarified values. Public Telegram calls are separate observations and do not validate video claims, model behavior, or fills. Exact fidelity remains `NOT_MEASURABLE`.

## PR code mapped to the claims

| PR #992 file and functions | Code behavior at the audited head | Evidence boundary |
|---|---|---|
| `research/rbfn_options/core/rbfn_engine.py` — `GaussianRBFNetwork.fit`, `predict` | Implements a Gaussian radial basis function network. It z-score normalizes inputs, clips normalized values to `[-4, 4]`, selects center samples at deterministic indices `floor((j + 0.5) * N / K)`, uses Gaussian activations, and solves ridge-regularized weights with an unregularized bias. Defaults are 28 centers, width 3.4, and ridge 4.0. | Confirms the implementation uses an RBF network. The center selection is deterministic sample indexing, not sorting feature values and selecting feature quantiles. Nothing establishes that OptionMate uses this architecture or these parameters. |
| `research/rbfn_options/core/spot_boundary_model.py` — `CausalSpotBoundaryModel.extract_features_and_targets`, `fit`, `forecast_session` | Uses six prior-session features: prior range/close; prior close-open relative to range; prior close-low relative to range; five-day mean range/close; six-session close change; and prior open relative to the close two sessions earlier. Targets are current-session upper excursion, lower excursion, and close change, each scaled by the prior session range. Defaults use the RBF settings above. | These are the PR's features and targets, not recovered OptionMate inputs or labels. |
| `research/rbfn_options/core/spot_boundary_model.py` — `CausalSpotBoundaryModel.forecast_session`, `SpotBoundaryForecast.is_in_dead_zone`, `evaluate_touch` | Forecasting produces three spot levels: upper reversal, trend decider, and lower reversal. `is_in_dead_zone` defaults to a band of ±0.15% around the decider. `evaluate_touch` checks one upper and one lower level. `forecast_session` repairs order: if lower is not below upper, it substitutes a symmetric span around prior close and centers the decider; otherwise, if the decider is outside the boundaries, it clamps the decider inside them. | Video evidence shows multiple chart/spot overlays, while translated count wording is ambiguous; the complete count and construction are unverified. The fallback and clamping behavior are PR implementation choices; no evidence says OptionMate applies this repair. |
| `research/rbfn_options/core/spot_boundary_model.py` — `validate_structural_reversal` | Defaults to a 0.35 wick ratio. If volume history is supplied, the volume condition is at least 0.8 times its median; when history is missing, that condition defaults to confirmed. The implementation does not enforce the docstring's suggested candle-close condition. | These are implementation details of the structural reversal validator, not rules established by the recording. |
| `research/rbfn_options/core/low_premium_strike_selector.py` — `MultiStrikeChainRanker.rank_chain_at_timestamp`, `select_low_premium_strike`, `select_strike_at_touch` | Defines six premium tiers: ₹38, ₹48, ₹58, ₹68, ₹88, and ₹128. The chain ranker scores tier distance and, when available, spread penalty; its default spread penalty weight is 0.5. No delta term appears in the tier rank score. | These hardcoded implementation tiers are distinct from the user's `USER_CLARIFICATION` about model-derived premium values and are not a verified OptionMate selection algorithm. |
| `research/rbfn_options/core/strike_reversal_replay.py` — `ReversalReplayEngine.replay_session` | Defaults include lot size 50, stop 10 premium points, target 20 premium points, maximum hold 45 minutes, signal window 09:20–14:15, and next-bar-open entry after a close crossing from at/below to strictly above the reference level. Entry and exit fills apply configured half-spread and slippage; default values are 0.25 points each per side. It requires reward/risk of at least 2:1, gives the stop precedence if stop and target occur in one candle, and can apply a breakeven trailing stop when supplied. | These are explicit replay mechanics, not mechanics established by the recording. The crossing rule models an upward reclaim and cannot by itself establish the recording's full set of trend and reversal behaviors. |

The PR changed-file bundle does not contain end-to-end wiring from spot touch evaluation through CE/PE selection into replay. The listed components therefore should not be described as a single integrated strategy pipeline based on the changed files alone.

For Analyst `TQA-992-05`, repair counts and repair sensitivity are unavailable from the result artifacts, as is whether `validate_structural_reversal` was used to produce the reported results. No conclusion is drawn about those points.

## Local supplemental data not admitted to holdout

These supplemental files and provenance observations are separate from the exact PR changed-file bundle. They are not admitted as verified holdout evidence.

- In the isolated worktree, `research/rbfn_options/data/raw` is a symlink to `/Users/madhuram/tradebot/research/rbfn_options/data/raw`. The August/September Parquet exists at that resolved canonical path and was read-only inspected; it was not copied or modified. Its SHA-256 is `f570de53c267c42f2ea50672caa3b28bf80377be000eca85a85fb72354e23156`. It contains 31,570 rows across 41 sessions from 2026-08-03 through 2026-09-29, with one selected CE contract and one selected PE contract per session (385 minute bars per side per session). It has 82 rows at 09:19 and 738 rows after 15:30. Basic OHLC and duplicate checks pass.
- The canonical tree also contains `research/rbfn_options/fetch_upstox_aug_sep_options.py`. Redacted inspection of that script shows calls to Upstox v2 expired-instrument APIs, use of an access-token environment variable, derivation of 09:19 ATM from local spot, and requests for one CE and one PE at nearest expiry. This makes Upstox a declared/plausible source for the script's acquisition method, but no run log or source-response hashes bind the inspected Parquet to that exact script. Permission evidence is also absent, and one contract per side per day is not full-chain coverage. The file is absent from `raw_hashes`, `data_manifest`, and `verified_inputs`.
- The October processed-bar file is in the isolated worktree. Its SHA-256 is `d240ff81876ac7133338536a9072f960d10a91bed85fa080ce2801e66a784433`. It contains 7,736 rows across 15 sessions from 2026-10-07 through 2026-10-30, with 09:19 bars on six dates. `verified_inputs.json` explicitly excludes these rows. The run used 332,994 selected option rows through 2026-07-21.

Both supplements remain quarantined because source, permission, lineage, full-chain, and coverage gaps remain. No backtest rerun or result rewrite is represented here.

## Result integrity

The PR head contains multiple result artifacts with materially different scopes and outcome calculations, including `metrics_2026.json`, `trades_2026_optionmate_exact_single_trade.csv`, `trades_2026_full_year_jan_oct.csv`, `trades_2026_optionmate_exact_lines.csv`, and `coverage_by_date_contract.csv`. Their differing scopes and outputs prevent them from being treated as one consistent result set. This audit omits data-derived INR values and does not publish or validate a net P&L figure.

The positive artifact sum previously cited from `trades_2026_optionmate_exact_single_trade.csv` matches the PR body's reported figure, but is not retained here. The PR changed-file bundle includes no raw option data through October and no dedicated end-to-end generator or manifest for these October result files. Their data lineage and generation therefore are not demonstrated by that bundle.

## Test and CI evidence

- Separately recorded local video-analogue suite: **44 tests passed, with 4 subtests**; this is not the PR-focused suite.
- PR description claims **25 tests passed**; this review did not independently rerun that suite at the audited PR SHA.
- GitHub CI snapshot:
  - `Trusted base evidence coverage` — failed with `BLOCKING UNCLASSIFIED_CHANGED_PATH` entries.
  - `runtime-authority-base-authority` — exited 2; `git diff --check` reported trailing-whitespace findings.
  - `code-excellence-base-authority` — exited 1 with 38 findings and 0 blocks; reported `changed_paths=127`.
  - `unit_tests` — collection errored because module `core.research_registry.append_only_trial_ledger` was missing.
  - `pr818-live-flow-freeze-target` — failed with `PR818_FROZEN_LIVE_FLOW_VIOLATION`, naming `core/kite_depth_ws.py` against frozen SHA `d7dc45e7c5c76247e7d1b8abd40ec7682fac2f9b`. That path is not in the GitHub PR file list.
  - `agent-review-evidence` — failed because required docs were missing.
  - `code-excellence-gates` — exited 1 with 36 findings and 0 blocks; reported `changed_paths=116`.

This records observed check names and reported reasons. These CI and scope failures do not establish RBFN strategy defects, and they do not imply that every test failed. The CI snapshot is distinct from the local PR-focused test result. Passing tests can support behavior of tested code; they cannot establish that its behavior matches OptionMate.

## What is implemented, assumed, and unknown

**Implemented:** PR #992 contains an offline Gaussian RBF model, a three-level spot boundary forecast with level-order repair, dead-zone and touch checks, a structural reversal validator, a six-tier premium selector, and a replay engine with explicit triggers, stops, fill adjustments, costs, and exits.

**Assumed by the implementation:** the chosen features and targets, 28/3.4/4.0 model settings, the three-level forecast and repair rules, dead-zone and reversal-validation defaults, six selector tiers, crossing trigger, replay defaults, and artifact-specific data and calculation lineage.

**Cannot be known from the available evidence:** OptionMate's complete chart/spot overlay set, exact count and generation timestamps across sessions; whether/how these relate to premium outputs; its exact model inputs and mapping; its actual historical CE/PE choices, entries, exits, no-trade decisions, and fills; and whether any PR result variant reflects those decisions.

Tests and replay artifacts are not evidence of OptionMate fidelity. A result generated under PR-defined rules is not an independently verified OptionMate result or realized trading outcome.

## Verdict

**`NO-GO / RESEARCH-ONLY / NOT_MEASURABLE`.** PR #992 implements an offline research approach with some high-level concepts also present in translated video paraphrases. Its three-level model is not equivalent to the observed chart/spot overlays, whose exact count and construction remain unclear; its repair and selector behavior are implementation-specific, the changed files do not establish an end-to-end strategy pipeline, and the result artifacts conflict in scope and net outcome. The PR also includes runtime-facing paths outside the RBFN research area. The local supplemental files are not admitted to holdout evidence. The evidence does not support an exact-replication or profitability claim. No live execution is authorized.
