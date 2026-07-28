from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.trusted_option_data_joint_warehouse_v1.builder import classify_expired_options_root
from scripts.recover_upstox_expired_options_evidence_v1 import audit_root


EVIDENCE_ROOT = Path("/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1")


def test_recovered_root_reproduces_prior_counts() -> None:
    if not EVIDENCE_ROOT.exists():
        return
    audit = audit_root(EVIDENCE_ROOT)
    counts = audit["independent_counts"]
    assert audit["recovery_verdict"] == "RECOVERED_LOCAL_EVIDENCE"
    assert counts["populated_raw_contracts"] == 1199
    assert counts["normalized_1m_partitions"] == 1199
    assert counts["normalized_5m_partitions"] == 1199
    assert counts["missing_normalized_pairs"] == 0


def test_expired_options_root_classifies_as_trusted_derived() -> None:
    if not EVIDENCE_ROOT.exists():
        return
    row = classify_expired_options_root(EVIDENCE_ROOT)
    assert row["classification"] == "TRUSTED_DERIVED"
    assert row["has_strike"] is True
    assert row["has_expiry"] is True
    assert row["has_option_type"] is True
    assert row["has_bid_ask"] is False
    assert row["populated_contract_count"] == 1199


def test_contract_inventory_has_required_identity_columns() -> None:
    if not EVIDENCE_ROOT.exists():
        return
    frame = pd.read_parquet(EVIDENCE_ROOT / "manifests/contract_inventory.parquet")
    required = {"underlying", "expiry", "strike", "option_type", "normalized_1m_path", "normalized_5m_path"}
    assert required.issubset(frame.columns)
