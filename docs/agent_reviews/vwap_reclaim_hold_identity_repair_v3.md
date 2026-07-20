# VWAP Reclaim-Hold Identity Repair v3

Verified baseline: `a48176fc245375f15e316493364915ec37439e29`

Approved implemented pattern: `VWAP_RECLAIM_HOLD`

Compatibility identity preserved:

```text
STRATEGY_ID = vwap_reclaim_rejection_v1
MOVEMENT_TYPE = VWAP_RECLAIM_REJECTION
TEMPORAL_CONTRACT_VERSION = vwap_reclaim_causal_v1
```

Before behavior text:

```text
confirmed_vwap_reclaim_or_rejection
confirmed VWAP reclaim/rejection in a non-chop regime
reclaim_rejection
```

After behavior text:

```text
confirmed_vwap_reclaim_hold
confirmed VWAP reclaim and hold in a non-chop regime
reclaim_hold
```

Predicate changed: `NO`

Score changed: `NO`

Thresholds changed: `NO`

Rejection predicate added: `NO`

Evidence fields added:

```text
implemented_pattern = VWAP_RECLAIM_HOLD
compatibility_strategy_id = vwap_reclaim_rejection_v1
```

Validation:

```bash
pytest -q tests/test_vwap_trap_movement_strategies.py
python3 -m py_compile strategies/movement/vwap_reclaim.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
ruff check strategies/movement/vwap_reclaim.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
git diff --check
```

Result: `PASS`
