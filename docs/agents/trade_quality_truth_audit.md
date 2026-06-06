# Trade Quality Truth Audit

This audit is read-only. It inspects code and optional runtime snapshots to answer trade-quality truth questions without changing trading behavior.

## Purpose

- Prove whether fallback or recovered_fallback rows can still become executable.
- Identify where `confidence_raw` is computed and what components contribute to it.
- Distinguish true ranking from filter/display-only ordering.
- Separate candidate-pool truth from direct emit paths.
- Clarify whether UI rows are filtered snapshots or true ranked opportunities.

## Outputs

- `.runtime/trade_quality_audit/trade_quality_truth_audit_latest.json`
- `.runtime/trade_quality_audit/trade_quality_truth_audit_latest.md`
- Optional copies in `.runtime/agent_reports/`

## Safety

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `runtime_mutation_allowed=false`

## Run

```bash
PYTHONPATH=. python scripts/run_trade_quality_truth_audit.py \
  --repo-root . \
  --runtime-dir .runtime \
  --logs-dir logs \
  --out-dir .runtime/trade_quality_audit \
  --format both
```
