from __future__ import annotations

import json

import pandas as pd

from scripts.build_regime_model_comparison import build_regime_model_comparison


def test_build_regime_model_comparison_writes_regime_filters(tmp_path):
    src = tmp_path / "ev_labels.csv"
    rows = []
    for idx in range(80):
        rows.append(
            {
                "timestamp": f"2022-03-01T{9 + (idx // 30):02d}:{(idx % 30):02d}:00+00:00",
                "open": 100 + idx,
                "high": 101 + idx,
                "low": 99 + idx,
                "close": 100.5 + idx,
                "volume": 1000 + idx * 10,
                "future_return": 0.002 if idx % 3 == 0 else -0.001,
                "expected_value": 0.002 if idx % 3 == 0 else -0.001,
                "expected_value_bps": 20.0 if idx % 3 == 0 else -10.0,
                "ev_positive": int(idx % 3 == 0),
                "regime_tag": "TREND" if idx < 40 else "RANGE",
                "session_bucket": "OPEN" if idx < 40 else "MID",
            }
        )
    pd.DataFrame(rows).to_csv(src, index=False)

    out = tmp_path / "regime_report.json"
    csv_out = tmp_path / "regime_report.csv"
    md_out = tmp_path / "regime_report.md"
    report = build_regime_model_comparison(
        input_csv=src,
        output_json=out,
        output_csv=csv_out,
        output_md=md_out,
        label_column="ev_positive",
    )

    assert out.exists()
    assert csv_out.exists()
    assert md_out.exists()
    payload = json.loads(out.read_text())
    assert payload["models"]["logistic"]["rows"]
    assert payload["models"]["random_forest"]["rows"]
    assert payload["models"]["logistic"]["regime_filter"]
    assert report["output_json"] == str(out)
    assert report["output_csv"] == str(csv_out)
    assert report["output_md"] == str(md_out)
