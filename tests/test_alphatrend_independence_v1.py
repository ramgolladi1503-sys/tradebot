import pandas as pd

from research.alphatrend_mechanism_v1.independence import evaluate_nonoverlap


def _labeled_session(session: str, rows: int = 60) -> pd.DataFrame:
    timestamp = pd.date_range(f"{session} 09:15", periods=rows, freq="min")
    signal = [1 if i % 5 == 0 else 0 for i in range(rows)]
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "session_date": session,
            "signal": signal,
            "fwd_ret_15_bps": [2.0] * rows,
            "fwd_ret_30_bps": [3.0] * rows,
        }
    )


def test_dense_events_are_not_counted_as_independent():
    frame = _labeled_session("2026-08-03", rows=60)
    result = evaluate_nonoverlap(frame, "signal", horizons=(15, 30))

    assert result["horizons"]["15"]["raw_valid_n"] == 12
    assert result["horizons"]["15"]["nonoverlap_n"] == 4
    assert result["horizons"]["30"]["raw_valid_n"] == 12
    assert result["horizons"]["30"]["nonoverlap_n"] == 2


def test_nonoverlap_clock_resets_at_new_session():
    frame = pd.concat(
        [
            _labeled_session("2026-08-03", rows=31),
            _labeled_session("2026-08-04", rows=31),
        ],
        ignore_index=True,
    )
    result = evaluate_nonoverlap(frame, "signal", horizons=(30,))
    stats = result["horizons"]["30"]

    assert stats["nonoverlap_n"] == 4
    assert stats["sessions"] == 2
    assert stats["max_session_event_share"] == 0.5
