# EDGE-AI / OI-SHADOW Roadmap — Opportunity Intelligence Shadow Layer

## Purpose

Build a read-only, deterministic Opportunity Intelligence layer that proves whether Tradebot has real candidate-ranking edge without disturbing the current runtime, validation, broker safety, manual approval flow, review queue, or existing candidate contracts.

This roadmap exists to prevent duplicate work. The implementation must build on existing Tradebot foundations such as CandidateIntent contracts, candidate pool validation, executable truth firebreaks, scoring contracts, and offline learning artifacts. Do not recreate existing systems under new names.

## Core Principle

Observe first.  
Score second.  
Compare third.  
Influence later.  
Control last.

## Non-Duplication Rule

Before every PR, inspect the repo and classify the planned scope as one of:

- `ALREADY_IMPLEMENTED` — do not rebuild; only add missing tests/docs/evidence if necessary.
- `PARTIAL` — extend the existing module with the smallest safe patch.
- `MISSING` — create the new module.
- `OUT_OF_SCOPE` — do not touch it in this roadmap.

A PR is invalid if it duplicates an existing contract, creates a parallel candidate schema without an adapter reason, rewires strategies unnecessarily, weakens safety gates, or changes live/review behavior before explicit promotion.

## Hard Boundaries

- No live broker calls.
- No live order placement.
- No execution behavior changes.
- No manual approval behavior changes.
- No replacement of existing review queue ranking in early phases.
- No dashboard/UI work unless explicitly scoped by a later issue.
- No broad refactor.
- No fake ML, fake labels, or toy model claims.
- No future leakage: features must be captured at candidate generation/scoring time only.
- No promotion of an ML ranker until walk-forward evidence proves it beats the current rule ranker.
- Preserve existing CandidateIntent, executable truth, final score, and safety contracts unless explicitly changed.
- Add deterministic tests and evidence for every PR.

## Shadow Runtime Boundary

Early outputs, if/when scoped, must live under:

```text
runtime/opportunity_intelligence/
```

The shadow layer must be disabled by default and controlled by an explicit flag such as:

```text
OPPORTUNITY_INTELLIGENCE_SHADOW=1
```

When the flag is off, Tradebot behavior must remain unchanged.

## 21 Logical Work Packages

These are logical work packages, not permission to blindly create 21 duplicate PRs. If existing repo work already satisfies a package, mark it as reused and move to the next real missing gap.

### Phase 1 — Shadow Foundation / Reconciliation

1. **OI-01 — Opportunity Intelligence Architecture Contract**  
   Lock architecture, ownership, no-rewrite policy, schema boundaries, runtime boundaries, and safety non-goals. Reuse existing CandidateIntent and candidate pool contracts instead of replacing them.

2. **OI-02 — Shadow Runtime Output Boundary**  
   Add safe runtime path/writer boundaries only if missing. Writes must be separate, atomic where needed, and disabled by default.

3. **OI-03 — Candidate Snapshot Schema / Adapter Contract**  
   Define normalized candidate snapshot only as an adapter over existing contracts. Do not create a competing CandidateIntent.

4. **OI-04 — Existing Candidate Reader Adapter**  
   Read current candidate/review/evidence outputs without mutating them. This proves observation without interference.

5. **OI-05 — Evidence Provenance Mapper**  
   Map quote/data provenance such as live quote, recovered fallback, stale quote, missing quote, missing spread, and unknown source.

### Phase 2 — Truth Judgment

6. **OI-06 — Data Truth Judge v0**  
   Determine whether candidate data is rankable, advisory-only, watchlist-only, or blocked. Fallback/stale/missing data must fail closed.

7. **OI-07 — Shadow Candidate Status Classifier**  
   Assign shadow statuses such as EXECUTABLE, WATCHLIST, ADVISORY_ONLY, BLOCKED, or NO_TRADE based on evidence, not confidence alone.

8. **OI-08 — Shadow Evidence Report Validator**  
   Validate that shadow reports include candidate id, status, reasons, data truth, and safety flags.

### Phase 3 — Deterministic Scoring

9. **OI-09 — Setup Quality Scorer v0**  
   Score setup quality using existing evidence. Confidence alone cannot produce a high score.

10. **OI-10 — Liquidity and Execution Scorer**  
    Score spread, tick freshness, quote source, bid/ask/depth availability, and slippage risk.

11. **OI-11 — Regime Fit Scorer**  
    Score whether the candidate fits the current regime. Unknown or conflicting regime must limit score.

12. **OI-12 — Risk/Reward and Time Decay Scorer**  
    Score RR, stop/target availability, session timing, expiry/theta risk, and late-session decay.

13. **OI-13 — Composite Opportunity Score v0**  
    Combine setup, data truth, liquidity, regime fit, and risk/reward into an explainable deterministic opportunity score.

### Phase 4 — Ranking and No-Trade Intelligence

14. **OI-14 — Shadow Opportunity Ranker**  
    Rank candidates deterministically without changing current UI/review queue ranking.

15. **OI-15 — Duplicate Exposure Guard**  
    Group same-symbol/same-direction/same-expiry candidates and mark duplicate directional exposure.

16. **OI-16 — Shadow No-Trade Oracle**  
    Produce explicit no-trade evidence when no candidate clears executable thresholds or data quality is bad.

### Phase 5 — Comparison and Visibility

17. **OI-17 — Current vs Shadow Ranking Comparison Report**  
    Compare current emitted/displayed ordering against shadow intelligence and flag cases where current top candidates are shadow-blocked.

18. **OI-18 — Shadow Opportunity Report CLI**  
    Provide an offline command to inspect top opportunities, blocked candidates, no-trade reasons, and data quality without broker/live market dependency.

19. **OI-19 — Read-Only Shadow UI Panel**  
    Optional later UI panel. It must be hidden by default, read-only, and must not replace the review queue.

### Phase 6 — Learning Loop

20. **OI-20 — Shadow Candidate Outcome Journal**  
    Store what happened after all candidates, including blocked and unselected candidates, in replay/paper mode first.

21. **OI-21 — Strategy Expectancy and Shadow Learning Report**  
    Report strategy expectancy by regime, score-bucket performance, blocked-but-winner cases, ranked-high-but-failed cases, and fallback-candidate outcomes.

## Future ML Only After Evidence

Do not add ML before the deterministic shadow layer and outcome truth exist.

Future optional work after OI-21:

- OI-22 — Shadow Learning-to-Rank Dataset Builder
- OI-23 — Offline Ranker Training Harness
- OI-24 — Shadow ML Ranker Comparison
- OI-25 — Promotion Gate: Rule Ranker vs ML Ranker

## Definition of Done

This roadmap is done only when Tradebot can show, from historical/paper truth evidence, whether:

- Top-ranked executable candidates outperform random candidates.
- Top-ranked candidates outperform lower-ranked candidates.
- Ranking score correlates with realized forward R.
- Fallback/stale/liquidity-broken candidates remain blocked from execution.
- No-trade decisions are explicit and evidence-backed.
- Any ML shadow score beats or fails against current rule score transparently.

## Implementation Warning

Do not turn this into another PR loop. The goal is not more files. The goal is measurable truth:

```text
candidate -> features -> truth -> score -> rank -> outcome -> proof
```
