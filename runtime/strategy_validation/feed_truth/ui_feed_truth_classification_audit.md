# UI Feed Truth Classification Audit

## Context
This document tracks the audit of UI feed truth classification (Phase 4).

## Executable Separation
We verified that the `core/opportunity_ranking.py` read-only output forces `final_rank_score = 0.0` when `advisory_only` is true. We also ensured that `core/canonical_ranked_ui_adapter.py` forces `advisory_only: True` if `executable_candidate` is false or if `fallback_used` is explicitly found in `safety_flags`.

## Findings
- `executable_truth` is properly separating live vs. fallback candidates into `execution_allowed`.
- `opportunity_ranking` respects `advisory_only`.
- `canonical_ranked_ui_adapter` translates this correctly.
- `dashboard/ui/table_model.py` retains `advisory_only` through `CANONICAL_COLUMNS`.
