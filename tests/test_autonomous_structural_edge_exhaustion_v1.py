from __future__ import annotations

import numpy as np
import pandas as pd

from research.autonomous_structural_edge_exhaustion_v1 import common as C
from research.autonomous_structural_edge_exhaustion_v1 import discovery as D
from research.autonomous_structural_edge_exhaustion_v1 import outcomes as O
from research.autonomous_structural_edge_exhaustion_v1 import certification as K


class _M:
    pass


M = _M()
for module in (C, D, O, K):
    for name in dir(module):
        if not name.startswith("__"):
            setattr(M, name, getattr(module, name))


def _sessions(n: int = 220) -> list[str]:
    return [str(value.date()) for value in pd.bdate_range("2024-01-02", periods=n)]


def _tiny_assignment() -> pd.DataFrame:
    times = pd.date_range("2025-01-02 09:15", periods=8, freq="5min", tz=M.TZ)
    states = [0, 0, 1, 1, 2, 0, 1, 2]
    return pd.DataFrame(
        {
            "session_date": ["2025-01-02"] * 8,
            "timestamp": times,
            "split": ["observation"] * 8,
            "session_progress": np.linspace(0.0, 1.0, 8),
            "index_close": np.linspace(100.0, 101.0, 8),
            "index_ret1": [0.0] * 8,
            "index_ret3": [0.0] * 8,
            "index_vol6": [0.001] * 8,
            "state": states,
            "assignment_margin": [0.9] * 8,
            "confident": [True] * 8,
            "family": ["F"] * 8,
        }
    )


def test_four_way_split_is_chronological_and_sealed() -> None:
    sessions = _sessions()
    split = M.split_sessions(sessions)

    assert {key: len(value) for key, value in split.items()} == {
        "observation": 110,
        "replication": 44,
        "validation": 33,
        "unopened": 33,
    }
    assert split["observation"][0] == sessions[0]
    assert split["observation"][-1] < split["replication"][0]
    assert split["replication"][-1] < split["validation"][0]
    assert split["validation"][-1] < split["unopened"][0]
    assert split["unopened"][-1] == sessions[-1]


def test_observation_universe_cannot_be_rescued_by_future_coverage() -> None:
    sessions = _sessions()
    split = M.split_sessions(sessions)
    times = pd.date_range("09:15", periods=75, freq="5min").time
    rows: list[tuple[pd.Timestamp, object, str, float, float]] = []
    symbols = [f"S{i:02d}" for i in range(40)] + ["FUTURE_ONLY"]
    for session in sessions:
        for tm in times:
            stamp = pd.Timestamp.combine(pd.Timestamp(session).date(), tm).tz_localize(M.TZ)
            rows.append((stamp, pd.Timestamp(session).date(), M.INDEX_SYMBOL, 22000.0, 1000.0))
            for symbol in symbols[:40]:
                rows.append((stamp, pd.Timestamp(session).date(), symbol, 100.0, 1000.0))
            if session not in split["observation"]:
                rows.append((stamp, pd.Timestamp(session).date(), "FUTURE_ONLY", 100.0, 1000.0))
    frame = pd.DataFrame(rows, columns=["timestamp", "session_date", "symbol", "close", "volume"])
    index_rows, accepted = M.accepted_index_sessions(frame)
    authority = M.select_observation_universe(frame, index_rows, split)

    assert accepted == sessions
    assert authority["selected_count"] == 40
    assert authority["selected_symbols"] == [f"S{i:02d}" for i in range(40)]
    assert "FUTURE_ONLY" not in authority["selected_symbols"]
    assert authority["selection_scope"] == "observation_sessions_only"


def test_compressed_motif_signal_uses_first_chronological_completion() -> None:
    assigned = _tiny_assignment()
    signal = M.first_motif_signal(assigned, (0, 1, 2))

    assert signal == pd.Timestamp("2025-01-02 09:35", tz=M.TZ)


def test_precomputed_motif_signals_match_first_completion() -> None:
    assigned = _tiny_assignment()
    discovery = {
        "families": [
            {
                "family": "F",
                "motifs": [
                    {"motif_id": "F:M0", "family": "F", "motif": [0, 1, 2]},
                    {"motif_id": "F:M1", "family": "F", "motif": [2, 0]},
                ],
            }
        ]
    }
    signals = M.precompute_motif_signals(discovery, {"F": assigned})

    assert signals == {
        "F:M0": {"2025-01-02": pd.Timestamp("2025-01-02 09:35", tz=M.TZ)},
        "F:M1": {"2025-01-02": pd.Timestamp("2025-01-02 09:40", tz=M.TZ)},
    }


def test_fixed_horizon_outcome_enters_next_bar() -> None:
    times = pd.date_range("2025-01-02 09:15", periods=10, freq="5min", tz=M.TZ)
    prices = np.asarray([100.0, 101.0, 102.0, 104.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0])
    frame = pd.DataFrame(
        {
            "session_date": ["2025-01-02"] * 10,
            "timestamp": times,
            "session_progress": np.linspace(0, 1, 10),
            "index_close": prices,
            "index_ret3": [0.0] * 10,
            "index_vol6": [0.001] * 10,
            "split": ["observation"] * 10,
        }
    )
    lookup = M.build_outcome_lookup(frame)
    signal = times[0]
    result = lookup[("2025-01-02", int(signal.value), 3)]

    expected = float(np.log(108.0 / 101.0) * 10000.0)
    assert result["entry_timestamp"] == str(times[1])
    assert result["exit_timestamp"] == str(times[4])
    assert np.isclose(result["raw_return_bps"], expected, atol=1e-12, rtol=0.0)


def test_unopened_tail_is_not_accessed_without_robust_survivor() -> None:
    result = M.unopened_test(
        outcomes={"records": []},
        hypotheses={"hypotheses": []},
        assignments={},
        frame=pd.DataFrame(),
        screen={"results": []},
        wfa={"results": []},
        robust={"survivor_hypothesis_ids": []},
    )

    assert result["principal_verdict"] == "UNOPENED_NOT_ACCESSED_NO_ROBUST_AUTONOMOUS_SURVIVOR"
    assert result["unopened_sessions_scored"] is False
    assert result["tested_hypothesis_ids"] == []
    assert result["survivor_hypothesis_ids"] == []


def test_global_screen_rejects_concentrated_or_uncertain_replication() -> None:
    base_h = {
        "hypothesis_id": "H1",
        "family": "F",
        "motif_id": "M",
        "motif": [0, 1],
        "horizon_bars": 3,
    }
    outcomes = {
        "records": [
            {
                "hypothesis": base_h,
                "stats": {
                    "observation": {"directional_excess": {"n": 25, "mean_bps": 4.0, "median_bps": 2.0, "hit_rate": 0.64, "ci90": [1.0, 7.0], "sign_p": 0.02}},
                    "replication": {"directional_excess": {"n": 12, "mean_bps": 3.0, "median_bps": 1.0, "hit_rate": 0.58, "ci90": [-0.5, 7.0], "sign_p": 0.20}},
                    "validation": {"directional_excess": {"n": 0, "mean_bps": None, "median_bps": None, "hit_rate": None, "ci90": [None, None], "sign_p": 1.0}},
                },
            }
        ]
    }
    screen = M.structural_screen(outcomes)

    assert screen["principal_verdict"] == "NO_AUTONOMOUS_STRUCTURAL_EDGE_CANDIDATE_SURVIVED_SCREEN"
    assert screen["survivor_hypothesis_ids"] == []
    assert screen["results"][0]["gates"]["replication_ci90_lower_positive"] is False


def test_robustness_requires_high_cost_and_winner_removal_survival() -> None:
    events = []
    gross = [40.0] * 3 + [4.0] * 27
    for i, value in enumerate(gross):
        events.append(
            {
                "session_date": f"2025-01-{(i % 28) + 1:02d}",
                "split": "observation",
                "directional_gross_bps": value,
                "delayed_net_proxy_bps": value - M.COST_BPS,
                "shorter_net_proxy_bps": value - M.COST_BPS,
                "longer_net_proxy_bps": value - M.COST_BPS,
            }
        )
    outcomes = {"records": [{"hypothesis": {"hypothesis_id": "H1"}, "events": events}]}
    result = M.robustness(outcomes, {"survivor_hypothesis_ids": ["H1"]})

    assert result["survivor_hypothesis_ids"] == []
    gates = result["results"][0]["gates"]
    assert gates["ten_bps_cost_mean_positive"] is False
    assert gates["remove_best_10pct_mean_positive"] is False


def test_exhaustion_ledger_never_reopens_failed_family() -> None:
    discovery = {
        "families": [
            {"family": family, "motif_count": 1}
            for family in M.FAMILY_FEATURES
        ]
    }
    ledger = M.exhaustion_ledger(
        discovery,
        {"results": []},
        {"results": []},
        {"survivor_hypothesis_ids": []},
        {"survivor_hypothesis_ids": [], "unopened_sessions_scored": False},
    )

    assert ledger["all_predeclared_families_attempted"] is True
    assert ledger["failed_families_reopened"] is False
    assert {row["family"] for row in ledger["families"]} == set(M.FAMILY_FEATURES)
    assert all(row["family_reopen_authorized"] is False for row in ledger["families"])


def test_outcome_lookup_respects_explicit_split_authority() -> None:
    times = pd.date_range("2025-01-02 09:15", periods=8, freq="5min", tz=M.TZ)
    rows = []
    for split, session_date, base in (
        ("observation", "2025-01-02", 100.0),
        ("unopened", "2025-01-03", 200.0),
    ):
        for i, ts in enumerate(times):
            stamp = ts if session_date == "2025-01-02" else ts + pd.Timedelta(days=1)
            rows.append(
                {
                    "session_date": session_date,
                    "timestamp": stamp,
                    "session_progress": i / 7,
                    "index_close": base + i,
                    "index_ret3": 0.0,
                    "index_vol6": 0.001,
                    "split": split,
                }
            )
    frame = pd.DataFrame(rows)
    lookup = M.build_outcome_lookup(frame, {"observation"})

    assert {key[0] for key in lookup} == {"2025-01-02"}
    assert not any(key[0] == "2025-01-03" for key in lookup)
