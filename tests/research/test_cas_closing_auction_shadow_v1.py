from pathlib import Path
import importlib.util
import sys

import pandas as pd

MODULE = Path(__file__).parents[2] / "scripts" / "run_cas_closing_auction_shadow_v1.py"
spec = importlib.util.spec_from_file_location("cas_shadow", MODULE)
cas = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cas
assert spec.loader is not None
spec.loader.exec_module(cas)


def test_phase_boundaries_are_explicit():
    contract = cas.CasWindowContract()
    values = {
        "2026-08-04 15:14:59+05:30": "NORMAL_LATE_SESSION",
        "2026-08-04 15:15:00+05:30": "CAS_REFERENCE_TRANSITION",
        "2026-08-04 15:20:00+05:30": "CAS_ORDER_DISCOVERY",
        "2026-08-04 15:30:00+05:30": "CAS_MATCHING",
        "2026-08-04 15:35:00+05:30": "DERIVATIVE_CONVERGENCE",
    }
    for timestamp, expected in values.items():
        assert cas.classify_phase(pd.Timestamp(timestamp), contract) == expected


def test_nifty_timeline_anchors_to_last_pre_1515_price():
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-08-04 15:14:00+05:30",
                    "2026-08-04 15:15:00+05:30",
                    "2026-08-04 15:20:00+05:30",
                ]
            ),
            "symbol": ["NIFTY 50"] * 3,
            "price": [24400.0, 24410.0, 24500.0],
        }
    )
    timeline = cas.build_index_timeline(frame, cas.CasWindowContract())
    assert timeline.iloc[0].return_from_1515_bps == 0.0
    assert timeline.iloc[-1].return_from_1515_bps > 0.0


def test_constituent_breadth_detects_concentration():
    rows = []
    for index in range(40):
        symbol = f"S{index:02d}"
        start = 100.0
        end = 120.0 if index < 3 else 100.1
        rows.extend(
            [
                {
                    "timestamp": "2026-08-04 15:15:00+05:30",
                    "symbol": symbol,
                    "close": start,
                },
                {
                    "timestamp": "2026-08-04 15:35:00+05:30",
                    "symbol": symbol,
                    "close": end,
                },
            ]
        )
    result = cas.constituent_breadth(pd.DataFrame(rows), cas.CasWindowContract())
    assert result["available"] is True
    assert result["constituent_count"] == 40
    assert result["top3_absolute_move_share"] > 0.65
    assert result["broad_move"] is False


def test_claim_boundary_never_certifies_two_sessions():
    contract = cas.CasWindowContract()
    assert contract.derivative_end == "15:40:00"
