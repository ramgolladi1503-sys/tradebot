# Fresh FeedTruth Audit Proof Pack

This proof pack is read-only evidence. It does not change FeedTruth behavior, execution truth, ranking, Phase2, broker/order behavior, websocket recovery, or dashboard/UI logic.

## What it proves

1. An old bad FeedTruth evidence sample still fails audit when it reports a top executable candidate under blocked/unknown truth.
2. A fixed blocked candidate sample passes audit when it stays non-executable under blocked/unknown truth.
3. A live fresh candidate sample passes audit when FeedTruth is live, trusted, and blocker-free.
4. The audit remains strict and read-only.

## Inputs

- `tests/fixtures/feedtruth_audit/old_bad_unknown_top_executable.jsonl`
- `tests/fixtures/feedtruth_audit/old_bad_unknown_top_executable.runtime.json`
- `tests/fixtures/feedtruth_audit/new_good_unknown_blocked_candidate.jsonl`
- `tests/fixtures/feedtruth_audit/new_good_unknown_blocked_candidate.runtime.json`
- `tests/fixtures/feedtruth_audit/live_fresh_good_candidate.jsonl`
- `tests/fixtures/feedtruth_audit/live_fresh_good_candidate.runtime.json`

## CLI

```bash
python scripts/run_feedtruth_audit_proof_pack.py --out-dir /tmp/feedtruth_proof_pack
cat /tmp/feedtruth_proof_pack/summary.md
```

The CLI writes:

- `old_bad_unknown_top_executable.report.json`
- `new_good_unknown_blocked_candidate.report.json`
- `live_fresh_good_candidate.report.json`
- `summary.md`

## Expected verdicts

- Old bad fixture: `FAIL`, contradiction count `> 0`
- New fixed blocked fixture: `PASS`, contradiction count `0`
- Live fresh good fixture: `PASS`, contradiction count `0`

## Safety proof

Every report remains read-only:

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `live_order_action=false`
- `broker_order_action=false`

## Validation

- `PYTHONPATH=. pytest -q tests/test_feed_truth_audit.py tests/test_feed_truth_audit_proof_pack.py -vv`
- `PYTHONPATH=. python scripts/run_feedtruth_audit_proof_pack.py --out-dir /tmp/feedtruth_proof_pack`
- `PYTHONPATH=. pytest -q tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_feed_truth_audit_proof_pack.py tests/test_feed_runtime_states.py tests/test_kite_depth_restart.py tests/test_kite_depth_ws_stability.py -vv`
- `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- `git diff --check`
- `PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr483_changed_paths.txt`
