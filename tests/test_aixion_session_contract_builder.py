from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import gzip
import json
import pytest
from scripts.build_trade_intelligence_session_contract import ContractBuildError, build_contract


def _master(path: Path) -> Path:
    expiry = int(datetime(2026, 8, 25, 15, 29, 59, tzinfo=timezone.utc).timestamp() * 1000)
    rows = [{"segment": "NSE_INDEX", "name": "Nifty 50", "instrument_type": "INDEX", "instrument_key": "NSE_INDEX|Nifty 50", "trading_symbol": "NIFTY"}, {"segment": "NSE_FO", "name": "NIFTY", "underlying_symbol": "NIFTY", "underlying_key": "NSE_INDEX|Nifty 50", "instrument_type": "FUT", "instrument_key": "NSE_FO|FUT1", "expiry": expiry}]
    path.write_bytes(gzip.compress(json.dumps(rows).encode("utf-8"))); return path


def test_builder_derives_exact_index_and_nearest_future(tmp_path: Path):
    master = _master(tmp_path / "complete.json.gz")
    contract = build_contract(instrument_master=master, trade_date=date(2026, 8, 5), index_name="Nifty 50", underlying_symbol="NIFTY", include_nearest_future=True, max_pair_lag_seconds=1.0, required_metrics=("index_path", "futures_basis"), require_capture_instruments=True)
    analytics = contract["analytics_contract"]; assert analytics["index_instrument"] == "NSE_INDEX|Nifty 50"; assert analytics["futures_instrument"] == "NSE_FO|FUT1"; assert analytics["max_pair_lag_seconds"] == 1.0; assert contract["expected_instruments"] == ["NSE_FO|FUT1", "NSE_INDEX|Nifty 50"]


def test_builder_requires_authoritative_pair_lag_for_future(tmp_path: Path):
    with pytest.raises(ContractBuildError, match="max-pair-lag"):
        build_contract(instrument_master=_master(tmp_path / "complete.json.gz"), trade_date=date(2026, 8, 5), index_name="Nifty 50", underlying_symbol="NIFTY", include_nearest_future=True)


def test_builder_rejects_ambiguous_index(tmp_path: Path):
    master = _master(tmp_path / "complete.json.gz"); rows = json.loads(gzip.decompress(master.read_bytes())); rows.append(dict(rows[0])); master.write_bytes(gzip.compress(json.dumps(rows).encode("utf-8")))
    with pytest.raises(ContractBuildError, match="exactly one index"):
        build_contract(instrument_master=master, trade_date=date(2026, 8, 5), index_name="Nifty 50")
