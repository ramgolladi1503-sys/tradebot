from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.option_e2e_recertification_v4.contract_reconstruction_v4_2.build_reconstruction import build_reconstruction


def test_v4_2_separates_observed_identity_from_current_master_enrichment(tmp_path) -> None:
    quote = tmp_path / "nifty_option_quotes.csv"
    pd.DataFrame(
        [
            {
                "timestamp": "2026-07-01T09:15:00+05:30",
                "instrument_key": "NIFTY2670125000CE",
                "instrument_token": "123",
                "underlying_symbol": "NIFTY",
                "option_right": "CE",
                "strike": 25000,
                "expiry": "2026-07-30",
                "bid": 1,
                "ask": 2,
            },
        ]
    ).to_csv(quote, index=False)
    current_master = tmp_path / "runtime" / "upstox_instruments" / "complete.json"
    current_master.parent.mkdir(parents=True)
    current_master.write_text(
        "[{\"instrument_key\":\"NIFTY2670125000CE\",\"instrument_token\":\"123\",\"underlying_symbol\":\"NIFTY\",\"instrument_type\":\"CE\",\"updated_at\":\"2026-07-01T00:00:00+05:30\"}]",
        encoding="utf-8",
    )

    records, summary = build_reconstruction(tmp_path)

    by_path = {record.logical_path: record for record in records}
    assert by_path["nifty_option_quotes.csv"].observed_row_identity is True
    assert by_path["nifty_option_quotes.csv"].observed_existence_status == "HISTORICAL_TOKEN_MAPPED_CONTRACT_AUTHORITY"
    assert by_path["nifty_option_quotes.csv"].historical_token_mapping_identity is True
    assert by_path["nifty_option_quotes.csv"].observed_underlying == "NIFTY"
    assert by_path["nifty_option_quotes.csv"].observed_option_right == "CE"
    assert by_path["runtime/upstox_instruments/complete.json"].current_master_enrichment is True
    assert by_path["runtime/upstox_instruments/complete.json"].observed_existence_status == "CURRENT_MASTER_DIAGNOSTIC_ONLY"
    assert by_path["runtime/upstox_instruments/complete.json"].observed_underlying == ""
    assert by_path["runtime/upstox_instruments/complete.json"].observed_option_right == ""
    assert summary["files_proving_historical_identity"] >= 1
    assert summary["current_master_diagnostic_matches"] >= 1


def test_v4_2_token_only_quote_stays_token_only_without_mapping(tmp_path) -> None:
    quote = tmp_path / "token_only_quote.csv"
    quote.write_text("timestamp,instrument_token\n2026-07-01T09:15:00+05:30,123\n", encoding="utf-8")

    records, summary = build_reconstruction(tmp_path)

    assert summary["files_total"] == len(records)
    assert summary["token_only_quote_files"] == 1
    assert summary["files_proving_observed_contract_existence"] == 0
    token_only_records = [record for record in records if record.observed_existence_status == "TOKEN_ONLY_QUOTE_NO_HISTORICAL_MAPPING"]
    assert token_only_records
    assert all(record.observed_underlying == "" for record in token_only_records)
    assert all(record.observed_option_right == "" for record in token_only_records)


def test_v4_2_rejects_timestamp_bid_ask_only_as_contract_identity(tmp_path) -> None:
    quote = tmp_path / "quote.csv"
    quote.write_text("timestamp,bid,ask\n2026-07-01T09:15:00+05:30,1,2\n", encoding="utf-8")

    records, _ = build_reconstruction(tmp_path)

    record = next(item for item in records if item.logical_path == "quote.csv")
    assert record.observed_row_identity is False
    assert record.observed_existence_status == "INSUFFICIENT_IDENTITY"
    assert record.observed_underlying == ""
    assert record.observed_option_right == ""
