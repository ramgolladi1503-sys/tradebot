from core.decision_telemetry import build_scan_summary


def test_build_scan_summary_counts_match():
    summary = build_scan_summary(
        symbol="NIFTY",
        total_candidates=12,
        accepted=2,
        rejected_by_reason={"spread_pct": 5, "low_volume": 3, "": 10},
        mode="PAPER",
        profile_name="PAPER_RELAXED",
    )

    assert summary["symbol"] == "NIFTY"
    assert summary["total_candidates"] == 12
    assert summary["accepted"] == 2
    assert summary["rejected_by_reason"] == {"spread_pct": 5, "low_volume": 3}
    assert summary["top_symbols_rejected"] == {"NIFTY": 8}
