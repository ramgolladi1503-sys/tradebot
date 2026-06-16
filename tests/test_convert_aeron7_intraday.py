from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.convert_aeron7_intraday import convert_aeron7_intraday


def test_convert_aeron7_intraday_writes_canonical_csv(tmp_path):
    source_root = tmp_path / "aeron7"
    input_dir = source_root / "2022" / "MAR" / "01MAR"
    input_dir.mkdir(parents=True)
    (input_dir / "NIFTY_F1.txt").write_text(
        "\n".join(
            [
                "NIFTY,20220301,09:15,16500,16510,16495,16505,1000,0",
                "NIFTY,20220301,09:20,16505,16525,16500,16520,1200,0",
            ]
        )
    )

    output_dir = tmp_path / "historical" / "index"
    report = convert_aeron7_intraday(source_root=source_root, output_dir=output_dir, symbols=["NIFTY_F1"])

    out_path = output_dir / "NIFTY_F1_intraday.csv"
    assert out_path.exists()
    assert report["rows_written"] == 2
    frame = pd.read_csv(out_path)
    assert list(frame.columns) == ["timestamp", "symbol", "open", "high", "low", "close", "volume"]
    assert frame["symbol"].tolist() == ["NIFTY", "NIFTY"]
    assert Path(report["written_files"][0]) == out_path


def test_convert_aeron7_intraday_skips_unwanted_symbols(tmp_path):
    source_root = tmp_path / "aeron7"
    input_dir = source_root / "2022" / "MAR" / "01MAR"
    input_dir.mkdir(parents=True)
    (input_dir / "BANKNIFTY.txt").write_text("BANKNIFTY,20220301,09:15,35000,35010,34990,35005,2000,0")

    output_dir = tmp_path / "historical" / "index"
    report = convert_aeron7_intraday(source_root=source_root, output_dir=output_dir, symbols=["NIFTY_F1"])

    assert report["rows_written"] == 0
    assert not list(output_dir.glob("*.csv"))
