from pathlib import Path

import pandas as pd

from scripts.audit_kite_candidate_replay_corpus import run_audit


def _write_underlying(root: Path, instrument: str, session: str) -> None:
    path = root / session / "underlying" / f"{instrument}_{session}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "date": pd.to_datetime([f"{session} 03:45:00+00:00", f"{session} 03:50:00+00:00"]),
            "open": [100.0, 101.0], "high": [102.0, 103.0],
            "low": [99.0, 100.0], "close": [101.0, 102.0],
            "volume": [1, 2], "instrument": [instrument, instrument],
            "instrument_token": [1, 1], "interval": ["5minute", "5minute"],
            "source": ["kite", "kite"], "synthetic": [False, False],
            "fallback": [False, False], "mock": [False, False],
            "fetch_date": [session, session],
        }
    ).to_parquet(path, index=False)


def test_complete_real_underlying_is_discovery_eligible(tmp_path: Path):
    session = "2025-01-02"
    for instrument in ("NIFTY", "BANKNIFTY", "SENSEX"):
        _write_underlying(tmp_path, instrument, session)
    report = run_audit(tmp_path)
    assert report["session_count"] == 1
    assert report["underlying_file_count"] == 3
    assert report["verdict"]["underlying_discovery_eligible"] is True


def test_mock_option_files_cannot_certify_profitability(tmp_path: Path):
    session = "2025-01-02"
    for instrument in ("NIFTY", "BANKNIFTY", "SENSEX"):
        _write_underlying(tmp_path, instrument, session)
    option = tmp_path / "20250102" / "options" / "NIFTY_OPT_MOCK_ltp.parquet"
    option.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": pd.to_datetime([f"{session} 03:45:00+00:00"]), "ltp": [100.0]}).to_parquet(option, index=False)
    report = run_audit(tmp_path)
    assert report["verdict"]["underlying_discovery_eligible"] is True
    assert report["verdict"]["option_profitability_validation_eligible"] is False
    assert report["verdict"]["mock_options_must_not_certify_strategy"] is True
