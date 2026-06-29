# Ranking Flow Gap Map

## Current flow

`strategy candidate -> trade builder -> soft reject / real filter -> executable truth filter -> scoring -> ranking -> top opportunity selection`

## Where the flow is strong

| Area | Evidence | Comment |
| --- | --- | --- |
| Hard separation of truth layers | `core/opportunity_scoring.py`, `core/candidate_ranking.py` | Scores, buckets, and ranks are separated from raw candidate creation |
| Read-only contract discipline | `read_only`, `is_order_action=false`, `broker_api_called=false` | Good safety posture |
| Feed-risk suppression | `core/candidate_ranking.py` | Stale/fallback/synthetic rows are not treated as clean executable rows |

## Where the flow is weak

| Gap | Current Behavior | Why It Matters |
| --- | --- | --- |
| Final score is still heuristic | Fixed component weights minus penalties | Can rank, but not prove edge |
| Bucket mapping can still feel like a survival order | Bucket priority and feed-risk suppression dominate | Surviving rows can be mistaken for validated opportunities |
| Probability labels are conditional | Only explicit outcome contracts get probability-like UI labels | Good, but still easy to misuse if not documented tightly |
| Missing calibration source | Some rows lack explicit calibration provenance | Prevents honest probability claims |
| Top opportunity can reflect filtered survivors | The best remaining row is not necessarily the best opportunity | Needs outcome-linked calibration |

## Ranking gap table

| File | Function/Class | Field | Current Behavior | Problem | Edge Impact | Required Fix Type |
| --- | --- | --- | --- | --- | --- | --- |
| `core/opportunity_scoring.py` | `score_candidate` | `final_score` | Weighted heuristic score with penalties and caps | Not outcome-calibrated | Can rank noise above true edge | Calibration |
| `core/opportunity_scoring.py` | `OpportunityScoreBreakdown` | `component_scores` | Component-wise explainability | Good diagnostics, not proof | May overstate precision | Keep + validate |
| `core/candidate_ranking.py` | `rank_candidates` | `bucket` | Safety bucket ordering | Survival can look like skill | Weak edge signal | Tighten labels + outcome proof |
| `core/candidate_ranking.py` | `CandidateRankRecord` | `probability_ui_label` | Shows probability-style text only when contract is explicit | Still easy to infer too much | Risk of misleading confidence | UI truth label fix |
| `core/opportunity_scoring.py` | `COMPONENT_WEIGHTS` | weights | Fixed mix of price/liquidity/freshness/regime/timing/confluence/volatility | Not regime-specific | Can flatten important regimes | Per-regime calibration |
| `core/opportunity_scoring.py` | `DOWNGRADE_REASON_PENALTIES` | penalties | Penalizes stale/fallback/wide-spread/unresolved-contract | Safety-first but heuristic | Good blocker, weak proof | Validate against outcomes |

## Selection truth

The live runtime evidence shows the bigger selection failure is upstream of ranking. When stale option quotes or regime uncertainty block the funnel, ranking never gets a fair chance to choose among strong candidates.

That means the ranking work is necessary, but it is not the primary current blocker.
