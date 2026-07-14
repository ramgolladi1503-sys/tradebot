from __future__ import annotations

from pathlib import Path

import pandas as pd

from core import orb_ohlcv_validation as mod


def _session_frame(start: str, *, base: float, instrument: str = "NIFTY", rows: int = 375) -> pd.DataFrame:
    stamps = pd.date_range(start=start, periods=rows, freq="1min", tz="Asia/Kolkata")
    out = []
    for idx, ts in enumerate(stamps):
        if idx < 15:
            price = base + (idx % 3) * 0.02
        else:
            price = base + 0.62 + (idx - 15) * 0.01
        out.append(
            {
                "timestamp": ts,
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price,
                "volume": 0,
                "instrument": instrument,
            }
        )
    return pd.DataFrame(out)


def _write_corpus(root: Path) -> Path:
    dates = [
        ("2026-07-01", 100.0),
        ("2026-07-02", 110.0),
    ]
    for day, base in dates:
        path = root / day.replace("-", "") / "underlying"
        path.mkdir(parents=True, exist_ok=True)
        _session_frame(f"{day} 09:15:00", base=base).to_parquet(path / f"NIFTY_{day.replace('-', '')}.parquet")
    return root


def _single_file_manifest(root: Path, relative_path: Path) -> dict[str, object]:
    path = root / relative_path
    df = pd.read_parquet(path)
    return {
        "schema_version": mod.MANIFEST_SCHEMA_VERSION,
        "source_root_placeholder": str(root),
        "selection_algorithm": {
            "name": "manual_test_manifest",
            "description": "Focused test manifest with one explicit session file.",
            "session_count": 1,
            "instrument": "NIFTY",
            "session_open": "09:15",
            "session_close": "15:29",
        },
        "selected_files": [
            {
                "relative_path": str(relative_path),
                "session_date": "2026-07-01",
                "instrument": "NIFTY",
                "source_category": "underlying_candle",
                "sha256": mod._file_hash(path),
                "file_size": path.stat().st_size,
                "row_count": int(len(df)),
                "columns": tuple(str(col) for col in df.columns),
                "dtypes": {str(col): str(dtype) for col, dtype in df.dtypes.items()},
                "first_timestamp": str(pd.Timestamp(df["timestamp"].iloc[0]).tz_convert("Asia/Kolkata").isoformat()),
                "last_timestamp": str(pd.Timestamp(df["timestamp"].iloc[-1]).tz_convert("Asia/Kolkata").isoformat()),
                "timestamp_timezone": "Asia/Kolkata",
                "duplicate_timestamp_count": 0,
                "monotonic_timestamp": True,
                "missing_values": {str(col): int(pd.to_numeric(df[col], errors="coerce").isna().sum()) for col in df.columns},
                "session_open_coverage": True,
                "session_close_coverage": True,
                "session_complete": True,
                "schema_fingerprint": mod._schema_fingerprint(tuple(str(col) for col in df.columns)),
                "eligibility": "ORB_INPUT_ELIGIBLE_WITH_CAUSAL_DERIVATIONS",
            }
        ],
        "generated_commit": "test",
        "manifest_hash": "placeholder",
    }


def test_source_manifest_is_deterministic_and_detects_missing_or_changed_files(tmp_path: Path) -> None:
    root = _write_corpus(tmp_path / "corpus")
    manifest_1 = mod.build_source_manifest(root, count=2)
    manifest_2 = mod.build_source_manifest(root, count=2)

    assert manifest_1["manifest_hash"] == manifest_2["manifest_hash"]
    assert manifest_1["selected_files"]
    assert all(item["eligibility"] == "ORB_INPUT_ELIGIBLE_WITH_CAUSAL_DERIVATIONS" for item in manifest_1["selected_files"])
    assert mod.verify_manifest_files(root, manifest_1) == []

    missing = manifest_1["selected_files"][0].copy()
    broken = dict(manifest_1)
    broken["selected_files"] = [missing]
    assert mod.verify_manifest_files(root / "missing", broken)

    changed_path = root / Path(manifest_1["selected_files"][0]["relative_path"])
    changed = pd.read_parquet(changed_path).copy()
    changed.loc[0, "close"] += 1
    changed.to_parquet(changed_path)
    problems = mod.verify_manifest_files(root, manifest_1)
    assert problems and problems[0]["problem"] == "hash_mismatch"


def test_layer_a_signals_are_causal_and_label_atr_proxy(tmp_path: Path) -> None:
    root = _write_corpus(tmp_path / "corpus")
    manifest = mod.build_source_manifest(root, count=2)
    frames = mod.load_selected_frames(root, manifest)
    strategy_info = mod.resolve_orb_strategy()

    signals = mod.build_layer_a_signals(frames, strategy_info=strategy_info)
    assert signals
    first = signals[0]
    assert first["signal_inputs"]["atr_volatility_z_proxy"] is not None
    assert first["candidate"]["strategy_id"] == "opening_range_retest_v1"
    assert first["candidate"]["movement_type"] == "OPENING_RANGE_RETEST"
    assert pd.Timestamp(first["signal_timestamp"]) >= pd.Timestamp("2026-07-01 09:30:00+05:30")


def test_next_bar_entry_is_strictly_later_and_missing_next_bar_rejects(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    path = root / "20260701" / "underlying"
    path.mkdir(parents=True, exist_ok=True)
    _session_frame("2026-07-01 09:15:00", base=100.0, rows=16).to_parquet(path / "NIFTY_20260701.parquet")
    manifest = _single_file_manifest(root, Path("20260701/underlying/NIFTY_20260701.parquet"))
    manifest_path = tmp_path / "manifest.json"
    mod.save_json(manifest_path, manifest)
    frames = mod.load_selected_frames(root, manifest)
    strategy_info = mod.resolve_orb_strategy()
    signals = mod.build_layer_a_signals(frames, strategy_info=strategy_info)
    assert signals

    research = mod.build_non_overlapping_research_trades(
        signals,
        frames,
        holding_minutes=15,
        friction_bps=2.0,
        entry_model="next_bar_open",
        overlap_policy="non_overlapping",
    )
    assert research["accepted_entries"] == []
    assert any(item["reason"] == "NO_LEGAL_NEXT_BAR" for item in research["rejections"])

    extended_root = tmp_path / "corpus2"
    path = extended_root / "20260701" / "underlying"
    path.mkdir(parents=True, exist_ok=True)
    _session_frame("2026-07-01 09:15:00", base=100.0, rows=18).to_parquet(path / "NIFTY_20260701.parquet")
    extended_manifest = _single_file_manifest(extended_root, Path("20260701/underlying/NIFTY_20260701.parquet"))
    extended_frames = mod.load_selected_frames(extended_root, extended_manifest)
    extended_signals = mod.build_layer_a_signals(extended_frames, strategy_info=strategy_info)
    accepted = mod.build_non_overlapping_research_trades(
        extended_signals,
        extended_frames,
        holding_minutes=15,
        friction_bps=2.0,
        entry_model="next_bar_open",
        overlap_policy="non_overlapping",
    )
    assert accepted["accepted_entries"]
    trade = accepted["accepted_entries"][0]
    assert pd.Timestamp(trade["signal_timestamp"]) < pd.Timestamp(trade["entry_timestamp"])


def test_non_overlapping_policy_rejects_while_active_and_resets_each_session(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    for day, base in [("2026-07-01", 100.0), ("2026-07-02", 120.0)]:
        path = root / day.replace("-", "") / "underlying"
        path.mkdir(parents=True, exist_ok=True)
        _session_frame(f"{day} 09:15:00", base=base, rows=18).to_parquet(path / f"NIFTY_{day.replace('-', '')}.parquet")
    manifest = {
        "selected_files": [
            {
                "relative_path": "20260701/underlying/NIFTY_20260701.parquet",
                "session_date": "2026-07-01",
                "instrument": "NIFTY",
                "sha256": mod._file_hash(root / "20260701/underlying/NIFTY_20260701.parquet"),
            },
            {
                "relative_path": "20260702/underlying/NIFTY_20260702.parquet",
                "session_date": "2026-07-02",
                "instrument": "NIFTY",
                "sha256": mod._file_hash(root / "20260702/underlying/NIFTY_20260702.parquet"),
            },
        ]
    }
    frames = mod.load_selected_frames(root, manifest)
    strategy_info = mod.resolve_orb_strategy()
    signals = mod.build_layer_a_signals(frames, strategy_info=strategy_info)
    research = mod.build_non_overlapping_research_trades(
        signals,
        frames,
        holding_minutes=15,
        friction_bps=2.0,
        entry_model="next_bar_open",
        overlap_policy="non_overlapping",
    )

    assert research["accepted_entries"]
    assert research["maximum_concurrency"] == 1
    assert research["overlapping_trade_count"] == 0
    assert research["cross_session_trade_count"] == 0
    assert any(item["reason"] == "POSITION_ALREADY_OPEN" for item in research["rejections"])


def test_future_mutation_does_not_change_earlier_signal(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    path = root / "20260701" / "underlying"
    path.mkdir(parents=True, exist_ok=True)
    frame = _session_frame("2026-07-01 09:15:00", base=100.0, rows=18)
    frame.to_parquet(path / "NIFTY_20260701.parquet")
    manifest = _single_file_manifest(root, Path("20260701/underlying/NIFTY_20260701.parquet"))
    frames = mod.load_selected_frames(root, manifest)
    strategy_info = mod.resolve_orb_strategy()
    signals_a = mod.build_layer_a_signals(frames, strategy_info=strategy_info)

    mutated = frame.copy()
    mutated.loc[17, "close"] += 50.0
    mutated.to_parquet(path / "NIFTY_20260701.parquet")
    mutated_frames = mod.load_selected_frames(root, manifest)
    signals_b = mod.build_layer_a_signals(mutated_frames, strategy_info=strategy_info)

    assert signals_a[0]["signal_identity"] == signals_b[0]["signal_identity"]
    assert signals_a[0]["signal_timestamp"] == signals_b[0]["signal_timestamp"]


def test_breaking_opening_range_boundary_suppresses_signals(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    path = root / "20260701" / "underlying"
    path.mkdir(parents=True, exist_ok=True)
    frame = _session_frame("2026-07-01 09:15:00", base=100.0, rows=40)
    frame.loc[:14, "high"] = frame.loc[:14, "high"] + 50.0
    frame.loc[:14, "close"] = frame.loc[:14, "high"]
    frame.to_parquet(path / "NIFTY_20260701.parquet")
    manifest = _single_file_manifest(root, Path("20260701/underlying/NIFTY_20260701.parquet"))
    frames = mod.load_selected_frames(root, manifest)
    strategy_info = mod.resolve_orb_strategy()
    signals = mod.build_layer_a_signals(frames, strategy_info=strategy_info)

    assert signals == []


def test_runner_writes_stable_json_and_separates_layers(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    path = root / "20260701" / "underlying"
    path.mkdir(parents=True, exist_ok=True)
    _session_frame("2026-07-01 09:15:00", base=100.0, rows=40).to_parquet(path / "NIFTY_20260701.parquet")
    manifest = _single_file_manifest(root, Path("20260701/underlying/NIFTY_20260701.parquet"))
    manifest_path = tmp_path / "manifest.json"
    mod.save_json(manifest_path, manifest)
    output = tmp_path / "results.json"
    payload = mod.run_orb_ohlcv_validation(
        candle_root=root,
        manifest_path=manifest_path,
        output_path=output,
        holding_minutes=15,
        friction_bps=2.0,
        entry_model="next_bar_open",
        overlap_policy="non_overlapping",
    )
    on_disk = output.read_text(encoding="utf-8")

    assert payload["verdict"] == "OHLCV_CANDLE_RESEARCH_ONLY"
    assert payload["signals"]
    assert payload["signal_forward_return_observations"]
    assert payload["accepted_entries"] == payload["complete_trades"]
    assert "\"OHLCV_CANDLE_RESEARCH_ONLY\"" in on_disk
