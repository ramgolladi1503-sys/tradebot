from __future__ import annotations

import pandas as pd
import pytest

from scripts import run_kite_underlying_directional_edge_campaign as campaign


def _bars(
    start: str = "2026-07-01 09:15:00+05:30",
    rows: int = 40,
    *,
    mock: bool = False,
):
    timestamps = pd.date_range(start, periods=rows, freq="5min")
    output = []
    price = 100.0
    for stamp in timestamps:
        price += 0.2
        output.append(
            {
                "date": stamp,
                "open": price,
                "high": price + 1,
                "low": price - 1,
                "close": price + 0.2,
                "volume": 1,
                "instrument": "NIFTY",
                "instrument_token": 1,
                "interval": "5minute",
                "source": "kite",
                "synthetic": False,
                "fallback": False,
                "mock": mock,
                "fetch_date": "2026-07-01",
            }
        )
    return output


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path)


def test_five_minute_files_are_not_labelled_one_minute(tmp_path) -> None:
    root = tmp_path / "kite"
    _write(
        root / "2026-07-01" / "underlying" / "NIFTY_2026-07-01.parquet",
        _bars(),
    )
    _, by_file, _, _ = campaign.audit_corpus(root)
    assert by_file[0]["bar_interval"] == "5minute"
    assert by_file[0]["authority_classification"] == "REAL_KITE_UNDERLYING_CANDLES"


def test_synthetic_fallback_mock_rows_are_excluded(tmp_path) -> None:
    root = tmp_path / "kite"
    _write(
        root / "2026-07-01" / "underlying" / "NIFTY_2026-07-01.parquet",
        _bars(mock=True),
    )
    sessions, by_file, _, rejected = campaign.audit_corpus(root)
    assert sessions == {}
    assert by_file[0]["authority_classification"] == "SYNTHETIC_OR_MOCK_ONLY"
    assert rejected["mock_true_rows"] == 40


def test_actual_files_drive_session_partitions(tmp_path) -> None:
    root = tmp_path / "kite"
    for day in [
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
        "2026-07-04",
        "2026-07-05",
    ]:
        _write(
            root / day / "underlying" / f"NIFTY_{day}.parquet",
            _bars(day + " 09:15:00+05:30"),
        )
    sessions, _, _, _ = campaign.audit_corpus(root)
    partition = campaign.build_partitions(sessions)
    assert partition["indexes"]["NIFTY"]["session_count"] == 5
    assert partition["indexes"]["NIFTY"]["holdout_dates"]
    assert partition["holdout_outcomes_read"] is False


@pytest.mark.parametrize(
    "function_name",
    ["generate_signals", "_simulate_signal", "_intent_rows", "_controls"],
)
def test_proxy_research_paths_are_removed(function_name: str) -> None:
    function = getattr(campaign, function_name)
    with pytest.raises(RuntimeError, match="proxy_"):
        function()


def test_compatibility_runner_delegates_to_canonical_campaign(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = {
        "campaign": "CANONICAL_UNDERLYING_TO_OPTION_INTENT_CAMPAIGN_V1",
        "verdict": "NO_CANONICAL_OPTION_INTENTS",
        "invocation_count": 0,
        "canonical_intent_count": 0,
        "holdout_outcomes_read": False,
    }
    calls = []

    def fake(kite_root, output_root, **kwargs):
        calls.append((kite_root, output_root, kwargs))
        return expected

    monkeypatch.setattr(campaign, "run_canonical_intent_campaign", fake)
    result = campaign.run_campaign(tmp_path, tmp_path / "out")
    assert result == expected
    assert calls
    assert calls[0][2]["underlyings"] == campaign.UNDERLYINGS
