from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import unquote

import pandas as pd
import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "ci"
    / "psilor_pr795_trusted_smoke.py"
)
spec = importlib.util.spec_from_file_location("psilor_pr795_trusted_smoke", MODULE_PATH)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.urls = []

    def get(self, url, *, headers, timeout):
        self.urls.append(url)
        assert timeout == 60
        assert headers["Authorization"] == "Bearer test-token"
        if "/expired-instruments/expiries" in url:
            return FakeResponse({"data": ["2026-07-28", "2026-08-04"]})
        if "/future/contract" in url:
            return FakeResponse(
                {
                    "data": [
                        {
                            "instrument_key": "NSE_FO|FUTURE",
                            "instrument_type": "FUT",
                        }
                    ]
                }
            )
        if "/option/contract" in url:
            options = []
            for kind in ("CE", "PE"):
                for strike in (24600, 24700, 24800, 24900):
                    options.append(
                        {
                            "instrument_key": f"NSE_FO|{kind}{strike}",
                            "instrument_type": kind,
                            "strike_price": strike,
                        }
                    )
            return FakeResponse({"data": options})
        if "/historical-candle/" in url:
            instrument = unquote(url.split("/historical-candle/", 1)[1].split("/", 1)[0])
            base = float(sum(instrument.encode("utf-8")) % 500 + 100)
            return FakeResponse(
                {
                    "data": {
                        "candles": [
                            ["2026-08-03T09:16:00+05:30", base, base + 2, base - 1, base + 1, 100, 10],
                            ["2026-08-04T09:16:00+05:30", base + 1, base + 3, base, base + 2, 110, 11],
                        ]
                    }
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")


def test_middle_contract_selection_is_deterministic():
    contracts = [
        {"instrument_key": "D", "strike_price": 400},
        {"instrument_key": "B", "strike_price": 200},
        {"instrument_key": "A", "strike_price": 100},
        {"instrument_key": "C", "strike_price": 300},
    ]
    selected = runner.select_middle_contracts(contracts)
    assert [item["instrument_key"] for item in selected] == ["B", "C"]


def test_validate_candles_rejects_conflicting_duplicate():
    candles = [
        ["2026-08-03T09:16:00+05:30", 100, 102, 99, 101, 10, 1],
        ["2026-08-03T09:16:00+05:30", 100, 103, 99, 102, 10, 1],
    ]
    with pytest.raises(runner.SmokeFailure) as captured:
        runner.validate_candles(candles, "NSE_FO|TEST")
    assert captured.value.verdict == "INVALID_SMOKE_RECONCILIATION"


def test_run_smoke_produces_exact_five_file_evidence(tmp_path):
    output = tmp_path / "smoke"
    result = runner.run_smoke(
        token="test-token",
        output_root=output,
        source_head_sha="abc123",
        session=FakeSession(),
    )

    assert result["smoke_verdict"] == runner.PASS_VERDICT
    assert result["source_head_sha"] == "abc123"
    assert result["real_future_contracts"] == 1
    assert result["real_ce_contracts"] == 2
    assert result["real_pe_contracts"] == 2
    assert result["real_candle_files"] == 5
    assert result["exact_common_sessions"] == ["2026-08-03", "2026-08-04"]
    assert result["smoke_hash_reconciliation"] == "PASS"
    assert result["credentials_persisted"] is False

    parquet_paths = sorted((output / "candles").glob("*.parquet"))
    assert [path.stem for path in parquet_paths] == [
        "CE_1",
        "CE_2",
        "FUTURE",
        "PE_1",
        "PE_2",
    ]
    for path in parquet_paths:
        frame = pd.read_parquet(path)
        assert frame["session_date"].tolist() == ["2026-08-03", "2026-08-04"]

    persisted = json.loads((output / "validation_report.json").read_text())
    assert persisted["smoke_verdict"] == runner.PASS_VERDICT
    assert persisted["formal_extraction_approved"] is True


def test_empty_token_fails_closed(tmp_path):
    with pytest.raises(runner.SmokeFailure) as captured:
        runner.run_smoke(
            token="",
            output_root=tmp_path / "smoke",
            source_head_sha="abc123",
            session=FakeSession(),
        )
    assert captured.value.verdict == "BLOCKED_AUTHENTICATION"


def test_request_rejects_non_relative_endpoint():
    with pytest.raises(runner.SmokeFailure) as captured:
        runner.request_json(
            FakeSession(),
            "test-token",
            "https://attacker.invalid/exfiltrate",
        )
    assert captured.value.verdict == "INVALID_FETCH_IMPLEMENTATION"
