from __future__ import annotations

from research.option_e2e_recertification_v4.authority_oracle_v4_1 import (
    AuthorityOracleInput,
    ContractIdentity,
    ContractMasterEvidence,
    LotSizeEvidence,
    ObservedUniverseEvidence,
    QuoteFileEvidence,
    QuoteRowEvidence,
    SourceManifestEvidence,
    verify_contract_authority,
)


def _identity(
    *,
    token: str = "12345",
    symbol: str = "NIFTY24JAN22000CE",
    expiry: str = "2024-01-25",
    strike: float = 22000.0,
    right: str = "CE",
) -> ContractIdentity:
    return ContractIdentity(
        instrument_token=token,
        trading_symbol=symbol,
        underlying="NIFTY",
        expiry=expiry,
        strike=strike,
        option_right=right,
    )


def _passing_input(**overrides: object) -> AuthorityOracleInput:
    target = _identity()
    base = AuthorityOracleInput(
        decision_ts="2024-01-24T10:00:00+05:30",
        target_identity=target,
        master=ContractMasterEvidence(
            identity=target,
            source_kind="point_in_time_master",
            created_at="2024-01-24T09:00:00+05:30",
            complete_universe=True,
        ),
        quote_file=QuoteFileEvidence(path="quotes/NIFTY24JAN22000CE.parquet", inferred_identity=target),
        quote_rows=(
            QuoteRowEvidence(
                identity=target,
                quote_ts="2024-01-24T09:59:59+05:30",
                row_expiry="2024-01-25",
                row_metadata={
                    "instrument_token": "12345",
                    "trading_symbol": "NIFTY24JAN22000CE",
                    "expiry": "2024-01-25",
                },
            ),
        ),
        manifest=SourceManifestEvidence(
            created_at="2024-01-24T09:05:00+05:30",
            dataset_hash="abc",
            row_count=1,
        ),
        observed_universe=ObservedUniverseEvidence(
            expected_identities=(target,),
            observed_identities=(target,),
        ),
        lot_size=LotSizeEvidence(observed_lot_size=50, independent_lot_size=50, source="historical_contract_terms"),
    )
    return AuthorityOracleInput(**{**base.__dict__, **overrides})


def test_full_quote_identity_proves_observed_existence_but_not_universe_completeness() -> None:
    target = _identity()
    missing = _identity(token="67890", symbol="NIFTY24JAN22100CE", strike=22100.0)
    verdict = verify_contract_authority(
        _passing_input(
            observed_universe=ObservedUniverseEvidence(
                expected_identities=(target, missing),
                observed_identities=(target,),
            )
        )
    )

    assert verdict.status == "FAIL"
    assert verdict.proves_observed_existence is True
    assert verdict.proves_universe_completeness is False
    assert verdict.reason_codes == ("observed_universe_incomplete",)


def test_current_master_alone_fails_authority() -> None:
    target = _identity()
    verdict = verify_contract_authority(
        _passing_input(
            master=ContractMasterEvidence(
                identity=target,
                source_kind="current_instrument_master",
                created_at="2024-01-24T09:00:00+05:30",
                complete_universe=True,
            )
        )
    )

    assert verdict.status == "FAIL"
    assert "current_master_alone_not_authority" in verdict.reason_codes


def test_quote_filename_alone_fails_authority() -> None:
    verdict = verify_contract_authority(_passing_input(quote_file=QuoteFileEvidence(path="NIFTY24JAN22000CE.parquet", inferred_identity=None)))

    assert verdict.status == "FAIL"
    assert "quote_filename_alone_not_authority" in verdict.reason_codes


def test_quote_row_without_expiry_fails_authority() -> None:
    target = _identity()
    verdict = verify_contract_authority(
        _passing_input(
            quote_rows=(
                QuoteRowEvidence(
                    identity=target,
                    quote_ts="2024-01-24T09:59:59+05:30",
                    row_expiry=None,
                    row_metadata={"instrument_token": "12345"},
                ),
            )
        )
    )

    assert verdict.status == "FAIL"
    assert "quote_row_without_expiry_not_authority" in verdict.reason_codes


def test_mismatched_token_or_symbol_fails() -> None:
    verdict = verify_contract_authority(_passing_input(quote_rows=(QuoteRowEvidence(identity=_identity(token="99999"), quote_ts="2024-01-24T09:59:59+05:30", row_expiry="2024-01-25"),)))

    assert verdict.status == "FAIL"
    assert "quote_row_identity_mismatch" in verdict.reason_codes
    assert verdict.proves_observed_existence is False


def test_mismatched_filename_and_row_metadata_fails() -> None:
    target = _identity()
    verdict = verify_contract_authority(
        _passing_input(
            quote_file=QuoteFileEvidence(path="quotes/NIFTY24JAN22000CE.parquet", inferred_identity=_identity(symbol="NIFTY24JAN22100CE", strike=22100.0)),
            quote_rows=(
                QuoteRowEvidence(
                    identity=target,
                    quote_ts="2024-01-24T09:59:59+05:30",
                    row_expiry="2024-01-25",
                    row_metadata={"instrument_token": "12345", "trading_symbol": "NIFTY24JAN22100CE", "expiry": "2024-01-25"},
                ),
            ),
        )
    )

    assert verdict.status == "FAIL"
    assert "quote_filename_identity_mismatch" in verdict.reason_codes
    assert "quote_row_metadata_mismatch" in verdict.reason_codes


def test_post_expiry_quote_fails() -> None:
    target = _identity()
    verdict = verify_contract_authority(
        _passing_input(
            decision_ts="2024-01-26T10:00:00+05:30",
            quote_rows=(
                QuoteRowEvidence(
                    identity=target,
                    quote_ts="2024-01-26T09:59:59+05:30",
                    row_expiry="2024-01-25",
                ),
            ),
        )
    )

    assert verdict.status == "FAIL"
    assert "post_expiry_quote" in verdict.reason_codes


def test_future_created_manifest_fails() -> None:
    verdict = verify_contract_authority(
        _passing_input(
            manifest=SourceManifestEvidence(
                created_at="2024-01-24T10:00:01+05:30",
                dataset_hash="abc",
                row_count=1,
            )
        )
    )

    assert verdict.status == "FAIL"
    assert "future_created_manifest" in verdict.reason_codes


def test_duplicate_conflicting_identities_fail() -> None:
    target = _identity()
    verdict = verify_contract_authority(
        _passing_input(
            quote_rows=(
                QuoteRowEvidence(
                    identity=target,
                    quote_ts="2024-01-24T09:59:58+05:30",
                    row_expiry="2024-01-25",
                ),
                QuoteRowEvidence(
                    identity=_identity(symbol="NIFTY24JAN22100CE", strike=22100.0),
                    quote_ts="2024-01-24T09:59:59+05:30",
                    row_expiry="2024-01-25",
                ),
            )
        )
    )

    assert verdict.status == "FAIL"
    assert "duplicate_conflicting_identities" in verdict.reason_codes


def test_lot_size_is_independently_gated() -> None:
    verdict = verify_contract_authority(
        _passing_input(
            lot_size=LotSizeEvidence(
                observed_lot_size=75,
                independent_lot_size=50,
                source="historical_contract_terms",
            )
        )
    )

    assert verdict.status == "FAIL"
    assert "lot_size_independent_mismatch" in verdict.reason_codes


def test_complete_independent_authority_passes_fail_closed_flags() -> None:
    verdict = verify_contract_authority(_passing_input())

    assert verdict.status == "PASS"
    assert verdict.reason_codes == ()
    assert verdict.proves_observed_existence is True
    assert verdict.proves_universe_completeness is True
    assert verdict.allowed_for_live_execution is False
    assert verdict.broker_api_called is False
    assert verdict.is_order_action is False
