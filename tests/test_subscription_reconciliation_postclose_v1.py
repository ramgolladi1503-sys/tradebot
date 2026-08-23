from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_subscription_reconciliation_postclose_v1.py"
spec = importlib.util.spec_from_file_location("subscription_reconcile_v1", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n")
    return path


def base(ts: float, *, consistent: bool = True) -> dict:
    intended = [256265, 260105, 265]
    subscribed = list(intended) if consistent else [256265, 265]
    missing = [] if consistent else [260105]
    return {
        "ts_epoch": ts,
        "run_id": "run-20260818",
        "feed_session_id": "feed-20260818",
        "runtime_state": "RUNNING",
        "feed_truth_state": "LIVE",
        "intended_tokens": intended,
        "subscribed_tokens": subscribed,
        "missing_tokens": missing,
        "extra_tokens": [],
        "pending_subscribe_tokens": [],
        "pending_unsubscribe_tokens": [],
        "pending_mode_full_tokens": [],
        "subscription_registry_consistent": consistent,
    }


def test_passes_when_all_supplied_snapshots_reconcile(tmp_path: Path):
    path = write_jsonl(tmp_path / "feed.jsonl", [base(1.0), base(2.0), base(3.0)])
    result = mod.reconcile([path])
    assert result["verdict"] == "PASS_POSTCLOSE_RECONCILIATION"
    assert result["inconsistent_rows"] == 0
    assert result["unknown_rows"] == 0
    assert result["final_subscription_registry_consistent"] is True
    assert result["broker_write_authority"] is False
    assert result["order_authority"] is False
    assert result["structural_edge_certified"] is False


def test_fails_on_any_observed_subscription_divergence(tmp_path: Path):
    path = write_jsonl(tmp_path / "feed.jsonl", [base(1.0), base(2.0, consistent=False), base(3.0)])
    result = mod.reconcile([path])
    assert result["verdict"] == "FAIL_SUBSCRIPTION_DIVERGENCE"
    assert result["inconsistent_rows"] == 1
    assert result["max_missing_tokens"] == 1
    assert result["divergence_windows"][0]["rows"] == 1


def test_unknown_fields_remain_unknown_not_zero(tmp_path: Path):
    row = {
        "ts_epoch": 1.0,
        "run_id": "run-20260818",
        "feed_session_id": "feed-20260818",
        "runtime_state": "RUNNING",
    }
    path = write_jsonl(tmp_path / "feed.jsonl", [row])
    result = mod.reconcile([path])
    assert result["verdict"] == "UNKNOWN_INCOMPLETE_SUBSCRIPTION_TRUTH"
    assert result["unknown_rows"] == 1
    assert result["max_missing_tokens"] is None
    assert result["max_pending_token_operations"] is None


def test_rejects_declared_missing_tokens_that_disagree_with_sets(tmp_path: Path):
    row = base(1.0, consistent=False)
    row["missing_tokens"] = []
    path = write_jsonl(tmp_path / "feed.jsonl", [row])
    with pytest.raises(ValueError, match="DECLARED_MISSING_TOKENS_MISMATCH"):
        mod.reconcile([path])


def test_rejects_declared_registry_consistency_that_disagrees_with_primitives(tmp_path: Path):
    row = base(1.0, consistent=False)
    row["subscription_registry_consistent"] = True
    path = write_jsonl(tmp_path / "feed.jsonl", [row])
    with pytest.raises(ValueError, match="DECLARED_REGISTRY_CONSISTENCY_MISMATCH"):
        mod.reconcile([path])


def test_pending_operations_prevent_consistency(tmp_path: Path):
    row = base(1.0)
    row["pending_subscribe_tokens"] = [999]
    row["subscription_registry_consistent"] = False
    path = write_jsonl(tmp_path / "feed.jsonl", [row])
    result = mod.reconcile([path])
    assert result["verdict"] == "FAIL_SUBSCRIPTION_DIVERGENCE"
    assert result["max_pending_token_operations"] == 1


def test_identity_drift_is_separate_failure(tmp_path: Path):
    first = base(1.0)
    second = base(2.0)
    second["feed_session_id"] = "feed-other"
    path = write_jsonl(tmp_path / "feed.jsonl", [first, second])
    result = mod.reconcile([path])
    assert result["verdict"] == "FAIL_IDENTITY_DRIFT"
    assert result["identity_consistent"] is False


def test_duplicate_json_keys_are_rejected(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"ts_epoch":1,"ts_epoch":2}\n')
    with pytest.raises(ValueError, match="JSON_DUPLICATE_KEY:ts_epoch"):
        mod.reconcile([path])


def test_symlink_inputs_are_rejected(tmp_path: Path):
    source = write_jsonl(tmp_path / "source.jsonl", [base(1.0)])
    link = tmp_path / "link.jsonl"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="INPUT_REGULAR_FILE_REQUIRED"):
        mod.reconcile([link])


def test_source_has_no_feed_or_broker_mutation_paths():
    text = SCRIPT.read_text(encoding="utf-8").lower()
    for forbidden in (
        "kiteconnect",
        "kiteticker",
        ".subscribe(",
        ".unsubscribe(",
        "place_" + "order(",
        "modify_" + "order(",
        "cancel_" + "order(",
    ):
        assert forbidden not in text
