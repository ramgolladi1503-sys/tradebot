# Stage 4 — PRE-CAS Matched Geometric Analogues

## Purpose

Stage 4 asks a descriptive question only after motifs have been frozen:

> when the first half of a historical window resembles a frozen motif, which replication windows continue to resemble the full motif and which geometrically diverge?

This is **not** a trade win/loss test. No future return, P&L, entry, exit, target, stop, CE/PE selection or live/paper authority is opened.

## Authority

Stage 4 V1 is deliberately `PRE_CAS` only.

The current pinned source ends on 2025-08-29 and contains no post-CAS sessions. POST_CAS must remain a separate, insufficient-data lane until enough sessions exist.

Input authorities:

- pinned external NIFTY Parquet SHA-256;
- frozen `native_motif_catalog.json`;
- observation / replication / unopened blocks already fixed by Stage 3.

## Disk policy

The stage reads the shared Git-LFS object directly and reconstructs the causal/native representation in memory.

It does **not** require:

- a Parquet checkout inside the sparse worktree;
- a new `runtime/` under the worktree;
- regeneration of the deleted causal trajectory Parquet.

Only the small analogue catalog and Markdown report are written.

## Definition of a matched geometric analogue

For each frozen motif:

1. reconstruct the frozen Stage-3 model deterministically;
2. fail closed unless observation/replication cluster counts exactly match the frozen motif catalog;
3. use the first 50% of each motif vector as the prefix;
4. calibrate prefix and full-geometry distance envelopes from observation members only using the 90th percentile;
5. score replication windows only;
6. call a replication window `geometry_completed` when its prefix qualifies and its full-window distance remains inside the observation-calibrated full-geometry envelope;
7. call it `geometry_diverged` when its prefix qualifies but its full-window geometry leaves that envelope.

`geometry_completed` and `geometry_diverged` are descriptive shape labels, not trading outcomes.

## Matching failures to completions

Each geometric divergence is paired, where possible, to a completion from a different session using only:

- prefix-vector distance;
- start-of-session progress proximity.

No second-half information is used to choose the match.

## Nearest historical prefixes

For each frozen motif, Stage 4 retains the nearest replication prefix analogues ranked by prefix distance and reports whether each later completed or geometrically diverged.

This is intended to expose what distinguishes apparently similar setups before any trading outcome is attached.

## CAS sensitivity annotation

Because the source is entirely PRE_CAS, Stage 4 adds only a time-of-day heuristic:

- `CAS_LOW_SENSITIVITY_CANDIDATE`
- `CAS_MEDIUM_SENSITIVITY`
- `CAS_HIGH_SENSITIVITY`
- `CAS_DIRECT_CLOSING_ZONE_REVALIDATION_REQUIRED`

This annotation is **not** post-CAS validation. Every motif remains `post_cas_validated=false` until separately proven with post-CAS sessions.

## Unopened block

The unopened Stage-3 sessions remain unopened.

Stage 4 may count how many windows exist in the unopened block but must not score, classify, rank or include them in analogue records.

## Outputs

- `matched_geometric_analogue_catalog.json`
- `ANALOGUE_RESULT.md`

## Allowed verdicts

- `PRE_CAS_MATCHED_GEOMETRIC_ANALOGUES_FROZEN`
- `NO_PRE_CAS_MATCHED_GEOMETRIC_ANALOGUE_AVAILABLE`

A deterministic reconstruction mismatch is a hard execution failure, not a negative market verdict.

## Explicit exclusions

Stage 4 does not calculate or infer:

- future return;
- trade direction;
- option side;
- entry / stop / target / exit;
- win rate;
- expectancy;
- profit factor;
- Sharpe;
- drawdown;
- P&L;
- live or paper authorization.

Only after Stage 4 evidence is frozen may the campaign proceed to a pattern-of-pattern transition graph and then hypothesis formulation.
