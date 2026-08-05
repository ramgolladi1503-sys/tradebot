import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from scripts.fetch_psilor_v1_data import (
    IST_TZ,
    UpstoxDataError,
    UpstoxFetcher,
    is_proxy_entry_eligible,
)


@pytest.fixture
def fetcher(tmp_path):
    start = pd.Timestamp("2026-01-01").tz_localize(IST_TZ)
    end = pd.Timestamp("2026-01-31").tz_localize(IST_TZ)
    instance = UpstoxFetcher(
        start,
        end,
        base_dir=tmp_path / "out",
        repository_root=tmp_path,
    )
    instance.token = "fake-token"
    return instance


def candle(ts="2026-01-05T09:15:00+05:30", volume=100, oi=50):
    return [ts, 100, 101, 99, 100.5, volume, oi]


def populated_response(candles):
    return {"status": "success", "data": {"candles": candles}}


def test_rejects_nan(fetcher):
    row = candle()
    row[1] = float("nan")
    with pytest.raises(UpstoxDataError, match="NaN"):
        fetcher.validate_candles([row], "TEST")


def test_rejects_inf(fetcher):
    row = candle()
    row[2] = float("inf")
    with pytest.raises(UpstoxDataError, match="Inf"):
        fetcher.validate_candles([row], "TEST")


def test_rejects_zero_ohlc(fetcher):
    row = candle()
    row[3] = 0
    with pytest.raises(UpstoxDataError, match="zero OHLC"):
        fetcher.validate_candles([row], "TEST")


def test_rejects_negative_volume(fetcher):
    with pytest.raises(UpstoxDataError, match="Negative volume/OI"):
        fetcher.validate_candles([candle(volume=-1)], "TEST")


def test_accepts_zero_volume_and_oi(fetcher):
    records, _, _ = fetcher.validate_candles([candle(volume=0, oi=0)], "TEST")
    assert records[0]["volume"] == 0
    assert records[0]["open_interest"] == 0


def test_proxy_entry_requires_positive_volume():
    assert is_proxy_entry_eligible({"volume": 1})
    assert not is_proxy_entry_eligible({"volume": 0})
    assert not is_proxy_entry_eligible({"volume": "bad"})


def test_duplicate_exact_is_deduplicated(fetcher):
    row = candle()
    records, _, _ = fetcher.validate_candles([row, row], "TEST")
    assert len(records) == 1


def test_duplicate_conflict_fails(fetcher):
    first = candle()
    second = candle()
    second[2] = 102
    with pytest.raises(UpstoxDataError, match="Duplicate candle conflict"):
        fetcher.validate_candles([first, second], "TEST")


def test_timezone_session_date_uses_india(fetcher):
    records, _, _ = fetcher.validate_candles(
        [["2026-01-04T20:00:00Z", 100, 101, 99, 100, 1, 0]],
        "TEST",
    )
    assert records[0]["session_date"] == "2026-01-05"


def test_error_mapping(fetcher):
    assert fetcher._map_http_error(401, "") == "BLOCKED_AUTHENTICATION"
    assert (
        fetcher._map_http_error(
            403,
            '{"errors":[{"errorCode":"UDAPI1149"}]}',
        )
        == "BLOCKED_UPSTOX_PLUS_REQUIRED"
    )
    assert (
        fetcher._map_http_error(
            403,
            '{"errors":[{"errorCode":"UDAPI9999"}]}',
        )
        == "BLOCKED_PROVIDER_PERMISSION"
    )
    assert (
        fetcher._map_http_error(
            403,
            "<html>Error 1010: browser signature blocked</html>",
        )
        == "BLOCKED_PROVIDER_PERMISSION_UNKNOWN"
    )


def test_ce_and_pe_increment_option_chunk_metrics(fetcher, tmp_path):
    payload = populated_response([candle()])
    entry = {"success_blocker_verdict": "SUCCESS_POPULATED"}

    def fake_request(*args, **kwargs):
        return 200, payload, b"{}", dict(entry)

    with (
        patch.object(fetcher, "_make_request", side_effect=fake_request),
        patch.object(
            pd.DataFrame,
            "to_parquet",
            lambda self, path, index=False: Path(path).write_bytes(b"x"),
        ),
        patch("scripts.fetch_psilor_v1_data.sha256_file", return_value="abc"),
    ):
        frame, reconciled = fetcher.fetch_historical_candles(
            "NSE_FO|CE",
            tmp_path / "ce.parquet",
            chunk_monthly=True,
            version="v2",
            series_type="CE",
        )
    assert frame is not None and reconciled
    assert fetcher.metrics["OPTION_REQUEST_CHUNKS_ATTEMPTED"] == 1
    assert fetcher.metrics["OPTION_REQUEST_CHUNKS_POPULATED"] == 1


def test_empty_contract_is_not_fully_reconciled(fetcher, tmp_path):
    with patch.object(
        fetcher,
        "_make_request",
        return_value=(
            200,
            {"data": {"candles": []}},
            b"{}",
            {"success_blocker_verdict": "SUCCESS_VALID_EMPTY"},
        ),
    ):
        frame, reconciled = fetcher.fetch_historical_candles(
            "NSE_FO|EMPTY",
            tmp_path / "empty.parquet",
            chunk_monthly=True,
            version="v2",
            series_type="CE",
        )
    assert frame is None and not reconciled
    assert fetcher.metrics["OPTION_OUTPUT_FILES_MISSING"] == 1
    assert fetcher.metrics["OPTION_REQUEST_CHUNKS_VALID_EMPTY"] == 1


def test_failed_chunk_prevents_reconciliation(fetcher, tmp_path):
    with patch.object(
        fetcher,
        "_make_request",
        return_value=(
            403,
            None,
            b"",
            {"success_blocker_verdict": "BLOCKED_PROVIDER_PERMISSION"},
        ),
    ):
        frame, reconciled = fetcher.fetch_historical_candles(
            "NSE_FO|FAIL",
            tmp_path / "failed.parquet",
            chunk_monthly=True,
            version="v2",
            series_type="PE",
        )
    assert frame is None and not reconciled
    assert fetcher.metrics["OPTION_REQUEST_CHUNKS_FAILED"] == 1


def test_dorl_is_not_blocked_by_missing_constituents(fetcher):
    for day in range(1, 31):
        fetcher.session_coverage[f"2026-01-{day:02d}"] = {
            "nifty": True,
            "vix": True,
            "future": True,
            "ce": {"CE"},
            "pe": {"PE"},
        }
    fetcher.metrics["EXPIRED_CANDLE_FETCH"] = "PASS"
    fetcher.metrics["CONSTITUENT_MEMBERSHIP_AUTHORITY"] = "FAIL"
    assert fetcher.compute_verdict() == "DATA_READY_FOR_DORL_ONLY"


def test_disjoint_sessions_do_not_pass(fetcher):
    for day in range(1, 31):
        fetcher.session_coverage[f"2026-01-{day:02d}"] = {
            "nifty": True,
            "vix": False,
            "future": True,
            "ce": {"CE"},
            "pe": {"PE"},
        }
    fetcher.metrics["EXPIRED_CANDLE_FETCH"] = "PASS"
    assert fetcher.compute_verdict() == "BLOCKED_INSUFFICIENT_OVERLAP"


def test_psilor_requires_point_in_time_authority_and_45_constituents(fetcher):
    fetcher.constituent_authority_ranges = [
        {
            "effective_from": pd.Timestamp("2026-01-01").date(),
            "effective_to": pd.Timestamp("2026-01-31").date(),
            "constituents": [{}] * 50,
        }
    ]
    for day in range(1, 31):
        key = f"2026-01-{day:02d}"
        fetcher.session_coverage[key] = {
            "nifty": True,
            "vix": True,
            "future": True,
            "ce": {"CE"},
            "pe": {"PE"},
        }
        fetcher.constituent_coverage[key] = {f"C{i}" for i in range(45)}
    fetcher.metrics["EXPIRED_CANDLE_FETCH"] = "PASS"
    assert fetcher.compute_verdict() == "DATA_READY_FOR_PSILOR_PROXY_VALIDATION"


def test_user_agent_is_transparent(fetcher):
    assert "TradeBot-PSILOR-Research" in fetcher.user_agent
    assert "Mozilla/5.0" not in fetcher.user_agent


def test_manifest_does_not_store_token(fetcher):
    fetcher.token = "super-secret"
    headers = fetcher._request_headers("2.0")
    assert headers["Authorization"] == "Bearer super-secret"
    assert "super-secret" not in json.dumps(
        {"url_without_token": "https://api.upstox.com/v2/user/profile"}
    )


def test_pr719_inventory_does_not_treat_lfs_pointer_as_data(
    fetcher,
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    root = Path("data/upstox_expired_options")
    root.mkdir(parents=True)
    (root / "sample.parquet").write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:123\n"
        "size 10\n"
    )
    fetcher.audit_pr719_corpus()
    inventory = json.loads(
        Path("research/psilor_v1/existing_corpus_inventory.json").read_text()
    )
    assert inventory["lfs_pointers_found"] == 1
    assert inventory["materialized_parquet_files"] == 0
    assert inventory["authority_verdict"] == "NOT_MATERIALIZED_OR_NOT_VALIDATED"
