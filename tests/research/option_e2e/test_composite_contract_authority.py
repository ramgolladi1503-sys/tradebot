from __future__ import annotations

import pytest

from research.option_e2e_recertification_v4.composite_contract_authority import (
    QuoteContractEvidence,
    certify_quote_observed_existence,
)
from research.option_e2e_recertification_v4.contract_identity_oracle import assert_no_conflicting_identity
from research.option_e2e_recertification_v4.observed_contract_universe import ObservedUniverse
from research.option_e2e_recertification_v4.signal_contract import OptionRight


def _quote(**overrides) -> QuoteContractEvidence:
    data = {
        "observed_ts": "2024-01-25T10:00:00+05:30",
        "trading_symbol": "NIFTY24JAN22000CE",
        "instrument_token": "123",
        "underlying": "NIFTY",
        "option_right": OptionRight.CE,
        "strike": 22000.0,
        "expiry": "2024-01-25",
        "provider": "fixture",
        "source_hash": "hash",
        "bid": 99.0,
        "ask": 100.0,
        "filename_symbol": "NIFTY24JAN22000CE",
        "manifest_hash": "manifest",
    }
    data.update(overrides)
    return QuoteContractEvidence(**data)


def test_full_quote_identity_proves_observed_existence_not_universe_or_lot_size() -> None:
    verdict = certify_quote_observed_existence(_quote(), decision_ts="2024-01-25T10:01:00+05:30")
    assert verdict.observed_existence is True
    assert verdict.universe_completeness == "OBSERVED_CONTRACT_ONLY"
    assert verdict.lot_size_authority == "LOT_SIZE_AUTHORITY_MISSING"
    assert verdict.full_contract_authority is False


def test_quote_filename_or_missing_expiry_cannot_certify_contract() -> None:
    with pytest.raises(ValueError, match="missing_quote_contract_identity"):
        certify_quote_observed_existence(_quote(trading_symbol=""), decision_ts="2024-01-25T10:01:00+05:30")
    with pytest.raises(ValueError, match="missing_quote_expiry"):
        certify_quote_observed_existence(_quote(expiry=""), decision_ts="2024-01-25T10:01:00+05:30")


def test_mismatched_filename_post_expiry_and_future_manifest_fail() -> None:
    with pytest.raises(ValueError, match="filename_row_symbol_mismatch"):
        certify_quote_observed_existence(
            _quote(filename_symbol="NIFTY24JAN22000PE"),
            decision_ts="2024-01-25T10:01:00+05:30",
        )
    with pytest.raises(ValueError, match="post_expiry_quote"):
        certify_quote_observed_existence(
            _quote(observed_ts="2024-01-25T15:31:00+05:30"),
            decision_ts="2024-01-25T15:32:00+05:30",
        )
    with pytest.raises(ValueError, match="future_created_manifest"):
        certify_quote_observed_existence(
            _quote(file_created_ts="2024-01-25T10:02:00+05:30"),
            decision_ts="2024-01-25T10:01:00+05:30",
        )


def test_duplicate_conflicting_identity_and_incomplete_universe_fail_closed() -> None:
    assert_no_conflicting_identity((_quote(), _quote()))
    with pytest.raises(ValueError, match="duplicate_conflicting_contract_identity"):
        assert_no_conflicting_identity((_quote(), _quote(strike=22100.0)))
    universe = ObservedUniverse(
        decision_ts="2024-01-25T10:01:00+05:30",
        option_right=OptionRight.CE,
        contracts=(_quote(),),
        completeness_score=0.5,
        universe_label="OBSERVED_DATASET_UNIVERSE",
    )
    with pytest.raises(ValueError, match="observed_universe_incomplete"):
        universe.validate(min_completeness=0.95)
