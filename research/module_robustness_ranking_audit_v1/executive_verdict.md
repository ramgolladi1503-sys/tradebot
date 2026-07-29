# Executive Verdict

Principal outcome: RANKING_PIPELINE_NOT_TRUSTWORTHY

Audited module count: 4310
Excluded module count: 16634
P0/P1/P2/P3 counts: 1/3/2/1
Row accounting reconciles: PARTIALLY_VERIFIED for synthetic ranking probe only; full replay accounting is BLOCKED_BY_MISSING_EVIDENCE.
Every displayed row traceable to ranked candidate: NOT_VERIFIED; fallback UI sources are VERIFIED.
Ranking deterministic: PARTIALLY_VERIFIED for synthetic in-process probe.
Score semantics comparable: PARTIALLY_VERIFIED as heuristic setup scores; predictive calibration NOT_VERIFIED.
Fallback/degraded rows can reach executable state: PARTIALLY_VERIFIED blocked by executable-truth/ranking policies, but requires replay proof across UI/approval.

Top five repair priorities:
1. Require ranked candidate identity for every actionable displayed row.
2. Preserve fallback/degraded provenance across scoring, ranking, top-opportunity projection, and executable truth.
3. Add deterministic replay row-accounting fixtures with stage reconciliation.
4. Rename or gate uncalibrated confidence/probability labels as setup scores.
5. Add semantic contract tests for high-criticality row-surface modules lacking direct tests.

Explicit blockers:
- Primary checkout was dirty; audit used clean origin/main worktree.
- No live broker credentials were used or required.
- Full labelled out-of-sample calibration evidence was not present in this audit.
- Full historical row-flow accounting requires a selected frozen replay sample beyond static module inventory.
