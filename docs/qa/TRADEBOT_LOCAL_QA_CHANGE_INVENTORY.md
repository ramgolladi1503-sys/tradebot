# Tradebot Local QA Change Inventory

## Scope

Repository: `/Users/madhuram/tradebot`

Working branch for this QA slice: `ram/qa-edge-first-execution-guard-elite`

Reference PR line: `#543 - QA Gate Foundation + Fallback Executable Firewall`

Inventory timestamp basis: local untracked and modified files observed before staging any QA work for this slice.

## Classification Summary

- `KEEP_FOR_PR`: 0
- `REVIEW_BEFORE_KEEP`: 5
- `DROP_OR_IGNORE`: 21
- `UNKNOWN`: 0

## File Inventory

| Path | State | Purpose | Test Value | PR #543 | Risk | Decision |
|---|---|---:|---:|---|---|---|
| `.agents/skills/grill-me/SKILL.md` | untracked | local agent skill override | 2 | no | local tooling noise | DROP_OR_IGNORE |
| `.pr555_backup/staged_before_pr555_ci_fix.patch` | untracked | backup patch from unrelated PR 555 work | 1 | no | accidental scope bleed | DROP_OR_IGNORE |
| `.pr555_backup/uncommitted_before_pr555_ci_fix.patch` | untracked | backup patch from unrelated PR 555 work | 1 | no | accidental scope bleed | DROP_OR_IGNORE |
| `docs/agent_reviews/handoffs/codex-feed-soak-handoff-20260611.md` | untracked | handoff note from feed-soak work | 3 | no | stale cross-PR context | REVIEW_BEFORE_KEEP |
| `docs/code_excellence/reports/changed_paths.txt` | untracked | generated CE artifact | 1 | no | generated report should not ship | DROP_OR_IGNORE |
| `docs/code_excellence/reports/current_detailed.md` | untracked | generated CE artifact | 1 | no | generated report should not ship | DROP_OR_IGNORE |
| `docs/code_excellence/reports/unified_agent_elite_latest.md` | untracked | generated CE artifact | 1 | no | generated report should not ship | DROP_OR_IGNORE |
| `docs/code_excellence/reports/unified_ce_gate_latest.md` | untracked | generated CE artifact | 1 | no | generated report should not ship | DROP_OR_IGNORE |
| `docs/repo_forensics/reports/pr_gate_latest.md` | untracked | generated forensics report | 2 | no | generated artifact should not ship | DROP_OR_IGNORE |
| `docs/repo_forensics/reports/repo_map_latest.md` | untracked | generated forensics report | 2 | no | generated artifact should not ship | DROP_OR_IGNORE |
| `docs/superpowers/specs/2026-06-11-eight-year-backtest-strategy-edge-design.md` | untracked | unrelated backtesting design spec | 3 | no | scope contamination | REVIEW_BEFORE_KEEP |
| `fix_kite_depth_ws.py` | untracked | ad hoc runtime fix script | 2 | no | unsafe runtime drift | DROP_OR_IGNORE |
| `fix_test.py` | untracked | scratch test helper | 1 | no | junk file | DROP_OR_IGNORE |
| `fix_test2.py` | untracked | scratch test helper | 1 | no | junk file | DROP_OR_IGNORE |
| `fix_test3.py` | untracked | scratch test helper | 1 | no | junk file | DROP_OR_IGNORE |
| `fix_test4.py` | untracked | scratch test helper | 1 | no | junk file | DROP_OR_IGNORE |
| `fix_test5.py` | untracked | scratch test helper | 1 | no | junk file | DROP_OR_IGNORE |
| `fix_test6.py` | untracked | scratch test helper | 1 | no | junk file | DROP_OR_IGNORE |
| `fix_test7.py` | untracked | scratch test helper | 1 | no | junk file | DROP_OR_IGNORE |
| `fix_test8.py` | untracked | scratch test helper | 1 | no | junk file | DROP_OR_IGNORE |
| `fix_test9.py` | untracked | scratch test helper | 1 | no | junk file | DROP_OR_IGNORE |
| `fix_test10.py` | untracked | scratch test helper | 1 | no | junk file | DROP_OR_IGNORE |
| `prompts/jules/feed_stability_rca.md` | untracked | prompt material for unrelated RCA work | 2 | no | scope contamination | REVIEW_BEFORE_KEEP |
| `runtime/live_observation/` | untracked | live-observation runtime artifacts | 2 | no | generated live artifact | DROP_OR_IGNORE |
| `runtime/live_stop_review/20260611_142353/bad_events.txt` | untracked | generated live-stop review artifact | 2 | no | generated runtime artifact | DROP_OR_IGNORE |
| `runtime/live_stop_review/20260611_142353/candidate_flow_trace_latest.json` | untracked | generated live-stop review artifact | 2 | no | generated runtime artifact | DROP_OR_IGNORE |
| `runtime/live_stop_review/20260611_142353/feed_runtime_latest.json` | untracked | generated live-stop review artifact | 2 | no | generated runtime artifact | DROP_OR_IGNORE |
| `runtime/live_stop_review/20260611_142353/review.txt` | untracked | generated live-stop review artifact | 2 | no | generated runtime artifact | DROP_OR_IGNORE |
| `scratch.py` | untracked | scratch script | 1 | no | junk file | DROP_OR_IGNORE |
| `scratch_ticker.py` | untracked | scratch script | 1 | no | junk file | DROP_OR_IGNORE |
| `skills-lock.json` | untracked | local skill lock metadata | 1 | no | local tooling noise | DROP_OR_IGNORE |
| `update_artifacts.py` | untracked | local helper for artifact rewrites | 3 | no | could rewrite generated outputs | REVIEW_BEFORE_KEEP |

## Notes

- No tracked modified files existed at inventory time.
- The local tree contains multiple unrelated generated reports and scratch files. They must remain out of the QA PR.
- Nothing in this inventory should be staged automatically.
