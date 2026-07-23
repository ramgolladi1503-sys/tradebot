from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.option_e2e_recertification_v4.contract_reconstruction_v4_2.build_reconstruction import build_reconstruction


def test_v4_2_separates_observed_identity_from_current_master_enrichment(tmp_path) -> None:
    quote = tmp_path / "nifty_option_quotes.csv"
    pd.DataFrame(
        [
            {"timestamp": "2026-07-01T09:15:00+05:30", "instrument_key": "NIFTY2670125000CE", "bid": 1, "ask": 2},
        ]
    ).to_csv(quote, index=False)
    current_master = tmp_path / "runtime" / "upstox_instruments" / "complete.json"
    current_master.parent.mkdir(parents=True)
    current_master.write_text("[]", encoding="utf-8")

    records, summary = build_reconstruction(tmp_path)

    by_path = {record.logical_path: record for record in records}
    assert by_path["nifty_option_quotes.csv"].observed_existence_status == "SELF_DESCRIBING_QUOTE_AUTHORITY"
    assert by_path["runtime/upstox_instruments/complete.json"].current_master_enrichment is True
    assert by_path["runtime/upstox_instruments/complete.json"].observed_existence_status == "CURRENT_MASTER_DIAGNOSTIC_ONLY"
    assert summary["files_proving_historical_identity"] == 0
    assert summary["current_master_diagnostic_matches"] == 1


def test_v4_2_summary_is_derived_from_records(tmp_path) -> None:
    quote = tmp_path / "token_only_quote.csv"
    quote.write_text("timestamp,instrument_token\n2026-07-01T09:15:00+05:30,123\n", encoding="utf-8")

    records, summary = build_reconstruction(tmp_path)

    assert summary["files_total"] == len(records)
    assert summary["token_only_quote_files"] == 1
    assert summary["files_proving_observed_contract_existence"] == 0
    assert any(record.observed_existence_status == "TOKEN_ONLY_QUOTE_NO_HISTORICAL_MAPPING" for record in records)
