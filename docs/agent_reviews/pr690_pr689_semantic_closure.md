# PR 690 — PR 689 Semantic Closure Review

mode: RESEARCH_BACKTEST_PRODUCTION_REPAIR
candidate_id: PR690_PR689_SEMANTIC_CLOSURE
 decision: DRAFT_REVIEW_REQUIRED
reason: Post-merge inspection of PR 689 found three semantic defects not detected by its green CI: false rejection of rule-selected candidates, omission of canonical ledger validation from the mandatory discovery chain, and incomplete WFA folds reducing the promotion denominator.
timestamp: 2026-07-22T06:05:00+05:30
is_order_action: false
broker_api_called: false
source: GitHub PR 689 merged bytes and PR 690 regression evidence

## Agent Work Contract

Repair only the three independently reproduced semantic gaps remaining after PR 689. Preserve strategy formulas, thresholds, market-data ingestion, live execution, broker access, runtime risk controls, configuration, dashboards, and order permissions. Keep PR 690 draft and unmerged until all repository checks and human review complete.

## Scope Guard

In scope:

- Phase 4 selection-evidence ownership for ranked and rule-selected candidates;
- canonical mean-reversion trade-ledger validation inside the mandatory truth gate;
- certified WFA all-fold completeness and no-trade fold handling;
- focused positive and negative regression tests.

Out of scope:

- strategy optimization or threshold changes;
- historical result regeneration;
- broker, feed, execution, risk, dashboard, or production configuration changes;
- paper or live activation;
- unrelated cleanup or refactoring.

Files changed are limited to research/backtest audit, WFA, tests, and this review document.

## Grill Me Review

Adversarial questions applied:

1. Can a valid rule-selected candidate be rejected because it does not own a ranking score? The audit now accepts a real score or a finite positive cost-hurdle margin.
2. Can a candidate pass with neither score nor rule-selection evidence? No; missing evidence fails closed.
3. Can an explicit zero, negative, nonnumeric, or nonfinite cost margin pass? No; explicit invalid margin evidence blocks selection quality.
4. Can parameter discovery proceed while timestamp, P&L, RR, or ledger-schema evidence is invalid? No; the mandatory truth gate executes and embeds the canonical ledger audit.
5. Can a two-fold result be promoted as a three-fold WFA? No; any incomplete fold set is rejected before final parameter selection or holdout evaluation.
6. Can a no-trade test fold silently count as an evaluated fold? No; it is classified as `TEST_METRICS_INVALID` and the WFA is rejected.

## Hermes Review

Interface and compatibility review:

- existing `selected` and `status=PASSED` ownership remains unchanged;
- optional ranking score fields remain supported and are never synthesized from dimensional P&L;
- existing `cost_hurdle_margin` is used only as rule-selection evidence and retains its original units;
- existing audit classification names remain unchanged;
- the truth report adds embedded canonical ledger evidence without removing existing fields;
- the standalone ledger audit remains runnable without arguments and now additionally accepts `--strategy`;
- `run_walk_forward` retains its public parameters and report shape for complete folds;
- early rejection reports remain non-promoting and additive in blocker detail.

## GSD Review

Delivery is separated into three verifiable contracts:

- selection evidence accepts valid rule ownership and rejects missing or invalid evidence;
- canonical ledger integrity becomes mandatory through the existing truth-audit chain;
- WFA requires all three valid forward folds before holdout evaluation.

Each contract has both a valid-path regression and an unsafe or incomplete-path regression. No historical verdict is changed by this PR.

## QA / Safety Review

Regression coverage added or strengthened:

- positive cost-hurdle evidence passes without a fabricated rank score;
- missing score and cost evidence fails;
- nonpositive cost margin fails;
- canonical same-candle timestamp defect fails the truth gate;
- one fold with no valid parameters fails the WFA;
- one no-trade test fold fails the WFA;
- complete whole-session three-fold WFA remains promotable when all existing gates pass.

Safety boundaries:

- research-only execution flags are not changed;
- no broker module is imported or called by the changed paths;
- no order intent or order permission is created;
- no live or paper runtime path is modified;
- no strategy threshold is changed.

## High-Risk Path Review

No configured high-risk production path is changed. The modified scripts can influence research promotion decisions, so the review treats false approval and false rejection as high-impact analytical risks. The patch therefore uses fail-closed behavior for missing evidence while preserving legitimate rule-selected candidates.

## Acceptance Proof

Acceptance requires all of the following on one immutable branch head:

- focused Phase 4 audit tests pass;
- focused WFA integrity tests pass;
- full repository tests and CI pass;
- Code Excellence Gates pass;
- CodeQL Advanced passes;
- Portfolio CI passes;
- Repo Forensics PR Gate passes;
- Agent Review Evidence Gate passes;
- Verify Strategy Registry passes;
- PR remains limited to the declared research/backtest scope;
- PR remains draft until human review.

## Runtime Proof Required After Merge

After merge, regenerate affected mean-reversion Phase 4 audit outputs and certified WFA reports from frozen inputs. Confirm that:

- rule-selected passed candidates are not rejected solely for absent rank scores;
- selected candidates retain positive finite cost-hurdle evidence;
- the canonical ledger report is emitted for every discovery pass;
- any canonical ledger defect blocks the truth audit and parameter discovery;
- all three WFA folds are evaluated before holdout use;
- no historical strategy is promoted without newly generated evidence.

Until regeneration, affected historical reports remain `UNTRUSTED_REQUIRES_RERUN`.

## What This PR Does Not Prove

- It does not prove structural edge or profitability.
- It does not certify tradable option execution economics.
- It does not validate historical artifacts without rerunning them.
- It does not authorize paper or live trading.
- It does not repair unrelated backtest engines or strategy implementations.

## Human Approval

Human review is required before marking PR 690 ready or merging it. Review should confirm the six-code-file scope, the additive audit contract, all-fold WFA behavior, and the final hosted-check results. This document provides evidence for review; it is not merge authorization.
