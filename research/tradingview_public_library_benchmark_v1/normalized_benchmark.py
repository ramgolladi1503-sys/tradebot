from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from . import benchmark as B
from .guarded_runtime import install

EXPECTED_SYMBOLS = {"NIFTY", "BANKNIFTY"}
EXPECTED_ROWS = 411_420
EXPECTED_ROWS_PER_SYMBOL = 205_710
EXPECTED_UNIQUE_SESSIONS = 2_743


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_normalized(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.read_csv(path)
    required = {"dt", "open", "high", "low", "close", "symbol", "session"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"normalized Aeron7 artifact missing columns: {missing}")
    frame = frame.rename(columns={"dt": "timestamp", "session": "session_date"})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame["session_date"] = frame["session_date"].astype(str)
    frame["symbol"] = frame["symbol"].astype(str).str.upper().str.strip()
    for col in ("open", "high", "low", "close"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    valid = (
        frame["timestamp"].notna()
        & frame["symbol"].isin(EXPECTED_SYMBOLS)
        & frame[["open", "high", "low", "close"]].notna().all(axis=1)
        & (frame[["open", "high", "low", "close"]] > 0).all(axis=1)
        & (frame["low"] <= frame[["open", "close"]].min(axis=1))
        & (frame["high"] >= frame[["open", "close"]].max(axis=1))
        & (frame["low"] <= frame["high"])
    )
    if not bool(valid.all()):
        raise ValueError(f"normalized Aeron7 artifact contains {int((~valid).sum())} invalid rows")

    frame = frame.sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
    duplicates = int(frame.duplicated(["symbol", "timestamp"]).sum())
    if duplicates:
        raise ValueError(f"normalized Aeron7 artifact contains {duplicates} duplicate symbol/timestamp rows")

    symbol_counts = frame["symbol"].value_counts().to_dict()
    if len(frame) != EXPECTED_ROWS:
        raise ValueError(f"normalized Aeron7 row count drift expected={EXPECTED_ROWS} actual={len(frame)}")
    if set(symbol_counts) != EXPECTED_SYMBOLS:
        raise ValueError(f"normalized Aeron7 symbols drift: {symbol_counts}")
    if any(int(symbol_counts[s]) != EXPECTED_ROWS_PER_SYMBOL for s in EXPECTED_SYMBOLS):
        raise ValueError(f"normalized Aeron7 per-symbol rows drift: {symbol_counts}")
    unique_sessions = int(frame["session_date"].nunique())
    if unique_sessions != EXPECTED_UNIQUE_SESSIONS:
        raise ValueError(
            f"normalized Aeron7 session count drift expected={EXPECTED_UNIQUE_SESSIONS} actual={unique_sessions}"
        )

    authority = {
        "principal_verdict": "NORMALIZED_AERON7_ARTIFACT_VERIFIED",
        "path": str(path),
        "sha256": file_sha256(path),
        "rows": int(len(frame)),
        "rows_by_symbol": {k: int(v) for k, v in sorted(symbol_counts.items())},
        "unique_sessions": unique_sessions,
        "min_timestamp": str(frame["timestamp"].min()),
        "max_timestamp": str(frame["timestamp"].max()),
        "source_repository": B.AERON_REPO,
        "source_years": [2012, 2023],
        "normalization_authority": "PR698_AERON7_PATTERN_MATRIX_ARTIFACT",
        "normalization_workflow_run": 29939857560,
        "normalization_artifact_id": 8537774653,
        "normalization_artifact_digest": "sha256:3c3974d931a74720bffc57a927d91a3d9da04a7af5a4770378527a2b479135b3",
    }
    authority["semantic_sha256"] = B.digest(authority)
    return frame, authority


def _specs_from_mapping(mapping: Mapping[str, Any]) -> list[B.MechanismSpec]:
    specs: list[B.MechanismSpec] = []
    for item in mapping.get("mechanisms", []):
        params = tuple(sorted((str(k), float(v)) for k, v in item.get("params", {}).items()))
        specs.append(B.MechanismSpec(str(item["family"]), params, str(item.get("derivation", ""))))
    return specs


def run_from_normalized(inventory: Mapping[str, Any], normalized_file: Path) -> dict[str, Any]:
    install()
    mapping = B.prepare_specs(inventory)
    specs = _specs_from_mapping(mapping)
    bars, source_authority = load_normalized(normalized_file)
    frame = B.build_features(bars)
    splits = {symbol: B.split_sessions(frame, symbol) for symbol in B.SYMBOLS}
    frame = B.add_split(frame, splits)

    nifty_outcomes = B.attach_outcomes(frame, specs, "NIFTY", splits["NIFTY"])
    bank_outcomes = B.attach_outcomes(frame, specs, "BANKNIFTY", splits["BANKNIFTY"])
    screen = B.structural_screen(nifty_outcomes)
    wfa = B.validation_wfa(nifty_outcomes, screen)
    robust = B.robustness(nifty_outcomes, wfa, bank_outcomes)
    final = B.holdout_test(frame, specs, nifty_outcomes, robust, "NIFTY")

    result = {
        "campaign": "tradingview_public_library_benchmark_v1",
        "mapping": mapping,
        "source_authority": source_authority,
        "bar_authority": {
            "principal_verdict": "PRE_NORMALIZED_CAUSAL_5MIN_OHLC_REUSED",
            "rows": int(len(bars)),
            "accepted_symbol_sessions": int(bars.groupby(["symbol", "session_date"]).ngroups),
            "accepted_dates": int(bars["session_date"].nunique()),
            "min_session": str(bars["session_date"].min()),
            "max_session": str(bars["session_date"].max()),
            "resampling_repeated_in_this_campaign": False,
        },
        "split_counts": {s: {k: len(v) for k, v in splits[s].items()} for s in B.SYMBOLS},
        "nifty_outcomes": nifty_outcomes,
        "banknifty_outcomes": bank_outcomes,
        "structural_screen": screen,
        "validation_wfa": wfa,
        "robustness": robust,
        "final_holdout": final,
        "final_authority": {
            "principal_verdict": (
                "TRADINGVIEW_EXTERNAL_HYPOTHESIS_HOLDOUT_SURVIVORS_REQUIRING_EXACT_SCRIPT_RECONSTRUCTION"
                if final["survivors"]
                else "NO_TRADINGVIEW_RECONSTRUCTED_PRICE_MECHANISM_SURVIVED_INDEPENDENT_CERTIFICATION"
            ),
            "inventory_scripts": int(inventory.get("unique_script_count", 0)),
            "mapped_scripts": sum(1 for r in mapping["script_rows"] if r["mechanism_signature"]),
            "unique_mechanisms": int(mapping["unique_mechanism_count"]),
            "tested_hypotheses": len(nifty_outcomes["records"]),
            "structural_screen_survivors": len(screen["survivor_hypothesis_ids"]),
            "validation_wfa_survivors": len(wfa["survivor_hypothesis_ids"]),
            "robustness_survivors": len(robust["survivor_hypothesis_ids"]),
            "holdout_scored": bool(final["holdout_scored"]),
            "holdout_survivors": len(final["survivors"]),
            "exact_tradingview_script_certified": False,
            "options_edge_certified": False,
            "shadow_authorized": False,
            "paper_authorized": False,
            "live_authorized": False,
            "order_authorized": False,
            "next_gate_if_survivor": "RECONSTRUCT_ASSOCIATED_SCRIPT_RULE_EXACTLY_THEN_RETEST_WITHOUT_PARAMETER_TUNING",
        },
    }
    result["semantic_sha256"] = B.digest(
        {k: v for k, v in result.items() if k not in {"nifty_outcomes", "banknifty_outcomes"}}
    )
    return result
