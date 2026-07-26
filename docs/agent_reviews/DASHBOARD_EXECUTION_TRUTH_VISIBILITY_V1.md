mode: READ_ONLY_DASHBOARD_TRUTH_VISIBILITY
candidate_id: dashboard_execution_truth_visibility_v1
decision: EXPOSE_CANONICAL_EXECUTION_TRUTH_WITHOUT_CHANGING_RUNTIME_DECISIONS
reason: Current execution contracts already demote fallback sources, but the advisory table omits the canonical fields needed for an operator to distinguish display-only or recovered-fallback rows from executable rows.
timestamp: 2026-07-26T09:20:00+05:30
research_only: false
read_only: true
is_order_action: false
broker_api_called: false
source: core/top_opportunity_executable_truth.py, dashboard/readers/snapshot_reader.py, dashboard/ui/table_model.py, and the operator UI issue report

# Dashboard Execution Truth Visibility v1

## Agent Work Contract

- source_agent: ChatGPT
- action: GENERATE_PATCH
- title: Make fallback and display-only execution truth explicit in the advisory table
- scope: Dashboard view-model columns, canonical read-only execution-truth derivation, focused tests, Agent Review, and changed-path reporting
- allowed_paths: `dashboard/ui/table_model.py`, one focused test file, this review, and changed-path reporting
- forbidden_paths: Strategies, scoring formulae, ranking order, opportunity selection, broker calls, orders, execution engine, feed, risk, capital allocation, runtime snapshots, and live or paper configuration
- expected_tests: Fallback legacy-executable contradiction, canonical ask truth, explicit advisory non-promotion, and required table-column visibility
- acceptance_proof: Focused tests and all permanent pull-request checks pass on the exact head

## Scope Guard

This change is display-only. It imports the existing canonical top-opportunity execution-entry truth classifier and stamps two UI fields:

- `ui_execution_truth`
- `ui_execution_truth_reason`

The advisory table also exposes the existing explicit row flag, quote source, execution entry/source/status, display entry/source/status, and any producer-stamped top-opportunity truth reason. No source row is mutated in storage and no runtime permission or selection decision changes.

## High-Risk Path Review

No high-risk runtime path is changed. The dashboard table model is read-only presentation code. The imported classifier is already used by the snapshot reader to demote invalid top-executable rows. This PR does not alter that classifier.

## Grill Me Review

Showing only `confidence_raw`, `candidate_class`, and a fallback badge leaves an operator unable to answer the decisive question: does the row have canonical execution-entry truth? A recovered-fallback row can therefore look numerically similar to a real row even though existing runtime contracts correctly block it.

The fix deliberately does not invent a new ranking score or infer strategy edge. It displays the existing execution truth and its reason. A legacy row with `is_executable=true` still displays that raw contradiction, but `ui_execution_truth=false` and `fallback_source_advisory_only` make the canonical verdict explicit.

## Hermes Review

The view model reuses `classify_top_opportunity_row` rather than duplicating fallback-source rules. UI executable truth requires both:

1. canonical execution-entry truth from the existing classifier; and
2. an explicit `is_executable=true` row flag.

A canonical ask entry on a row explicitly marked advisory is therefore not promoted; it receives `canonical_entry_but_row_not_marked_executable`.

## GSD Review

The implementation changes one production presentation file and adds one focused test file. It does not introduce a new dashboard service, snapshot schema, persistence layer, or execution contract. Existing active and review table views remain unchanged; the additional columns appear only in the advisory view.

## QA / Safety Review

Focused controls prove:

- recovered-fallback quote or entry sources cannot visually pass canonical execution truth;
- canonical ask execution entry plus explicit executable flag produces true UI truth;
- canonical entry plus explicit advisory flag stays non-executable;
- advisory view includes both display-entry and execution-entry provenance fields.

Safety fields:

- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- no runtime row mutation
- no ranking, scoring, selection, or execution changes

## Acceptance Proof

Publication requires:

- four focused tests passing;
- full deterministic repository tests passing;
- Agent Review gate passing;
- Code Excellence with zero blocks;
- CodeQL, forensics, registry, and portfolio checks passing;
- exact final head recorded in the PR body.

## Runtime Proof Required After Merge

Open the advisory table with a snapshot containing:

- one `recovered_fallback` row carrying stale legacy executable fields;
- one canonical ask-backed executable row;
- one canonical ask-backed advisory row.

Verify the table visibly distinguishes all three using `ui_execution_truth`, `ui_execution_truth_reason`, raw `is_executable`, quote source, and display/execution entry provenance. No order or broker action is required.

## What This PR Does Not Prove

This work does not prove that scores are well calibrated, that ranking has edge, that BUY/SELL or CE/PE distributions are balanced, that capital allocation is optimal, or that fallback rows should be hidden. It does not alter candidate generation or opportunity ranking.

The broader issue report also raises score compression, directional bias, candidate-pool design, and capital allocation. Those require separate evidence and must not be smuggled into this UI-truth patch.

## Human Approval

Human approval remains required before changing score ownership, ranking formulae, strategy directionality, candidate selection, capital allocation, or any execution behaviour.
