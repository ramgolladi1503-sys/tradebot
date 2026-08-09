# NIFTY Swing Transition Cross-Session Audit V1

**Verdict:** `NIFTY_SWING_TRANSITION_PRIOR_EVIDENCE_INVALIDATED_CROSS_SESSION_SOURCE_DEFECT`

Research only. Runtime authority remains `NONE`. Broker actions remain prohibited. No edge is claimed.

## Scope

This audit explains the reduction from 60 development `UPTREND_CONTINUATION_SWING` episodes to 31 bounded-anatomy episodes and determines whether the prior development survivor can be trusted.

## Exact prior evidence

Prior NIFTY swing-transition development reported:

- `UPTREND_CONTINUATION_SWING` development episodes: **60**
- survivor count: **1**
- survivor direction: `UP`
- locked outcomes accessed: `false`
- prior motif SHA-256: `6daad77489fe032d8b78354ec4a00e89f69975df7085d09fd2c50c492a1953ec`

Prior bounded anatomy reported:

- development survivor episodes presented to anatomy: **60**
- anatomy episodes retained: **31**
- `missing_motif_join = 0`
- `missing_context_join = 0`
- locked outcomes accessed: `false`

## Root cause A — cross-session motif composition

The source function `swing_motifs()` in `scripts/research/hypothesis_factory/build_market_structure_motif_atlas_v1.py` walked consecutive pivots globally and did not require the three pivots to share a trading session.

The anatomy runner independently required all three pivot timestamps plus confirmation timestamp to belong to the episode session. Therefore cross-session swing motifs admitted by the source builder were removed only at anatomy time.

For `UPTREND_CONTINUATION_SWING`, every source motif contains exactly three pivots by construction. The prior run reported zero missing motif joins and zero missing context joins. Pivot and confirmation timestamps originate from the same canonical input rows. The remaining anatomy exclusion is the same-session condition. Thus the observed **29 episode difference (60 - 31)** is attributable to source motifs spanning session boundaries.

## Root cause B — cross-session swing labels

A second source defect was found during the repair review. `confirm_pivots()` correctly reset directional pivot discovery at each session boundary, but `classify_swings()` retained the previous same-type pivot globally. Therefore labels such as `HIGHER_HIGH`, `HIGHER_LOW`, `LOWER_HIGH`, `LOWER_LOW`, `DOUBLE_TOP_LIKE`, and `DOUBLE_BOTTOM_LIKE` could compare today's pivot with a pivot from a prior trading session.

That means simply dropping explicitly cross-session three-pivot motifs was insufficient: a physically same-session motif could still inherit a cross-session label. The prior motif generation is therefore invalid at both the motif-composition and swing-label layers.

## Why this invalidates the prior survivor

This is not missing evidence and not a statistical-gate issue. It is a **source-behavior defect**. An intraday chart swing structure may not bridge an overnight/session boundary or inherit yesterday's swing-relative label unless that behavior is explicitly designed and frozen. The prior NIFTY motif contract did not authorize either behavior.

Because the development outcome screen included motifs generated under these defects, its 60-episode population and resulting `DEVELOPMENT_ASYMMETRY_PASS` are not authoritative. The 31-episode anatomy artifact is also not promotable because it was selected from an invalid upstream population rather than regenerated from a corrected source universe.

## Repairs

### Motif session-scope repair

Commit:

`7445b87d670263bea5271bc9a80bc9faf322e8e4`

The motif builder now requires:

- every three-pivot swing motif to have one non-null session across all pivots;
- every five-pivot triangle motif to have one non-null session across all pivots.

### Swing-label session-scope repair

Commit:

`fcbb1f97d1ec058c22553146c3f3bf3ffc227a42`

The pattern-atlas builder now:

- records the pivot session at pivot creation;
- resets previous HIGH/LOW comparison state whenever the trading session changes;
- fails closed if a pivot reaches swing classification without a session;
- reports `swing_label_scope = SESSION_LOCAL`.

Zone interaction motifs already terminate at session boundaries and are not changed by this audit. Multi-session support/resistance-zone semantics remain a separate descriptive construct and are not used to rescue the invalid swing evidence.

## Superseded artifacts

The following prior NIFTY artifacts are evidence of an invalid source generation and MUST NOT authorize a locked test or edge claim:

- `NIFTY_motifs.jsonl` with SHA-256 `6daad77489fe032d8b78354ec4a00e89f69975df7085d09fd2c50c492a1953ec`
- `NIFTY_SWING_TRANSITION_FAMILY_V1_DEVELOPMENT.json`
- `NIFTY_SWING_TRANSITION_FAMILY_V1_DEVELOPMENT_EPISODES.jsonl` with SHA-256 `063579299febe7d90230e858524805f9954346b0e48d68802f0f03498e2aab74`
- `NIFTY_UPTREND_CONTINUATION_ANATOMY_V1.json`
- `NIFTY_UPTREND_CONTINUATION_ANATOMY_V1_EPISODES.jsonl` with SHA-256 `412b4f3ba74625f3af6cef2ded51d40cc119009063f02f54dc0dd88fd8d9ebd4`

They may be retained as provenance but are `SUPERSEDED_INVALID_SOURCE_GENERATION`.

The earlier NIFTY reversal-family development artifact used the same invalid motif generation and is also superseded. It must be rerun rather than treated as a valid negative result.

## Data boundary

The final 99 NIFTY sessions were not outcome-scored by the affected NIFTY development/anatomy stages. They remain reserved for future validation after clean same-session development regeneration.

## Required next action

1. Rebuild the NIFTY motif/context atlas from both repaired source layers.
2. Produce a new motif SHA and prove zero cross-session swing/triangle motifs.
3. Re-run the original frozen NIFTY reversal and swing-transition development families on the same first 394 sessions **without changing their gates**.
4. Only a survivor from the corrected population may enter a new bounded anatomy study.
5. Do not use the final 99 session outcomes until the corrected development/anatomy chain is frozen.

## Authority

- `RUNTIME_AUTHORITY=NONE`
- `BROKER_ACTIONS_PERMITTED=false`
- `EDGE_CLAIMED=false`
- `PAPER_TRADING_AUTHORIZED=false`
- `LIVE_TRADING_AUTHORIZED=false`
- `ORDER_AUTHORIZED=false`
