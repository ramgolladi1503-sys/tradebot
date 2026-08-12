from datetime import datetime, timezone
import pytest

from core.mros_program_contracts import (
    IndianSessionState, IntradayRegimeSpec, PredictionRecord,
    ProspectiveLedgerEntry, V2Hypothesis, seal_snapshot_metadata,
)


def test_three_index_state_rejects_missing_as_zero():
    state = IndianSessionState("2026-08-12", {"NIFTY": "a" * 64, "BANKNIFTY": "b" * 64, "SENSEX": "c" * 64}, False, ("SENSEX",))
    with pytest.raises(ValueError, match="INCOMPLETE"):
        state.validate()


def test_prediction_record_keeps_model_and_cutoff_identity():
    record = PredictionRecord("p" * 64, "m" * 64, datetime(2026, 8, 12, 9, tzinfo=timezone.utc), None)
    assert record.immutable_payload()["predicted_value"] is None


def test_ledger_rejects_outcome_timestamp_without_outcome():
    with pytest.raises(ValueError, match="MISMATCH"):
        ProspectiveLedgerEntry("p", None, datetime.now(timezone.utc), 1).validate()


def test_v2_hypothesis_requires_predeclared_v1_binding():
    with pytest.raises(ValueError, match="UNDECLARED"):
        V2Hypothesis("h", ("DXY",), "macro rationale", False, "v" * 64).validate()


def test_intraday_targets_cannot_be_relabelled_gap_target():
    IntradayRegimeSpec((30, 60, 120), "09:14:59", True, ("constant",)).validate()
    with pytest.raises(ValueError, match="TARGETS"):
        IntradayRegimeSpec((1,), "09:14:59", True, ("constant",)).validate()


def test_sealed_metadata_retains_execution_firewall():
    sealed = seal_snapshot_metadata({"source": "offline", "missing": True})
    assert sealed["read_only"] is True
    assert sealed["broker_write_authority"] is False
    assert sealed["order_authority"] is False
    assert sealed["paper_authorized"] is False
    assert sealed["live_authorized"] is False
