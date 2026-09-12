import pandas as pd

from research.alphatrend_mechanism_v1 import (
    AlphaTrendMechanismConfig,
    SIGNAL_COLUMNS,
    add_forward_labels,
    build_features,
    build_negative_controls,
)


def _bars(session="2026-08-03", rows=120, bearish=False):
    timestamp = pd.date_range(f"{session} 09:15", periods=rows, freq="min")
    values = []
    for i in range(rows):
        cycle = (0, 2, 5, 3, 1, 4)[i % 6]
        drift = -0.8 * i if bearish else 0.8 * i
        values.append(25000.0 + drift + (-cycle if bearish else cycle))
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "open": values,
            "high": [value + 1.5 for value in values],
            "low": [value - 1.5 for value in values],
            "close": [value + (-0.2 if bearish else 0.2) for value in values],
            "volume": [1000 + i for i in range(rows)],
        }
    )


def test_outputs_are_research_only_and_do_not_claim_proprietary_equivalence():
    out = build_features(_bars())
    assert out.attrs["research_only"] is True
    assert out.attrs["proprietary_equivalence_claimed"] is False
    assert out.attrs["mechanism"] == "ALPHATREND_INSPIRED_TRANSPARENT_V1"
    assert set(SIGNAL_COLUMNS).issubset(out.columns)


def test_future_bars_cannot_change_already_emitted_features():
    original = _bars(rows=120)
    mutated = original.copy()
    mutated.loc[80:, ["open", "high", "low", "close"]] += 500.0

    left = build_features(original).iloc[:80]
    right = build_features(mutated).iloc[:80]
    columns = [
        "trend_state",
        "momentum_state",
        "structure_state",
        "structure_label",
        "signal_full_fresh",
        "signal_continuation",
    ]
    pd.testing.assert_frame_equal(left[columns], right[columns])


def test_forward_labels_never_cross_session_boundary():
    day_one = _bars("2026-08-03", rows=40)
    day_two = _bars("2026-08-04", rows=40)
    out = add_forward_labels(pd.concat([day_one, day_two], ignore_index=True), horizons=(5,))
    last_day_one = out[out["session_date"] == "2026-08-03"].tail(5)
    first_day_two = out[out["session_date"] == "2026-08-04"].head(1)
    assert last_day_one["fwd_ret_5_bps"].isna().all()
    assert first_day_two["fwd_ret_5_bps"].notna().all()


def test_negative_controls_are_deterministic_and_session_scoped():
    day_one = build_features(_bars("2026-08-03", rows=80))
    day_two = build_features(_bars("2026-08-04", rows=80))
    frame = pd.concat([day_one, day_two], ignore_index=True)
    out = build_negative_controls(frame, "signal_continuation", shift_bars=7)

    inverse = out["signal_continuation__control_inverse"]
    assert (inverse == -out["signal_continuation"]).all()
    first_rows = out.groupby("session_date", sort=False).head(7)
    assert (first_rows["signal_continuation__control_shift_7"] == 0).all()


def test_continuation_events_exist_but_obey_cooldown():
    cfg = AlphaTrendMechanismConfig(continuation_cooldown_bars=5)
    out = build_features(_bars(rows=140), cfg)
    positions = out.index[out["signal_continuation"].ne(0)].tolist()
    assert positions
    assert all(right - left >= 5 for left, right in zip(positions, positions[1:]))


def test_bearish_synthetic_path_can_emit_negative_continuation():
    out = build_features(_bars(rows=140, bearish=True))
    signals = out.loc[out["signal_continuation"].ne(0), "signal_continuation"]
    assert not signals.empty
    assert (signals == -1).all()
