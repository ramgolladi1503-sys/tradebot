from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

import pandas as pd

from . import benchmark as B

FROZEN_TESTABLE_STATUSES = {
    "TESTABLE_EXACT_DESCRIPTION_CANDIDATE",
    "TESTABLE_CANONICAL_MECHANISM",
}


def guarded_prepare_specs(inventory: Mapping[str, Any]) -> dict[str, Any]:
    """Map only rows frozen as mechanically reproducible before outcomes.

    The inventory classification is an ex-ante gate. Rows classified as opaque/non-signal
    may not be promoted later merely because a generic primitive name was detected.
    """
    rows: list[dict[str, Any]] = []
    unique: dict[str, B.MechanismSpec] = {}
    counts: Counter[str] = Counter()

    for record in inventory.get("records", []):
        frozen = str(record.get("initial_status", ""))
        if frozen not in FROZEN_TESTABLE_STATUSES:
            if frozen == "DATA_INCOMPATIBLE":
                status = "INDEPENDENT_DATA_INCOMPATIBLE"
            elif frozen == "FETCH_FAILED":
                status = "FETCH_FAILED"
            else:
                status = "OPAQUE_OR_NON_SIGNAL"
            spec = None
        else:
            spec, status = B.map_record(record)

        counts[status] += 1
        rows.append(
            {
                "script_id": record.get("script_id"),
                "title": record.get("title"),
                "url": record.get("url"),
                "inventory_status": frozen,
                "benchmark_status": status,
                "mechanism_signature": spec.signature if spec else None,
                "family": spec.family if spec else None,
                "derivation": spec.derivation if spec else None,
            }
        )
        if spec is not None:
            unique.setdefault(spec.signature, spec)

    reconciled = sum(counts.values()) == int(inventory.get("unique_script_count", -1))
    payload = {
        "script_rows": rows,
        "benchmark_status_counts": dict(sorted(counts.items())),
        "unique_mechanism_count": len(unique),
        "mechanisms": [
            {
                "signature": s.signature,
                "family": s.family,
                "params": s.param_dict(),
                "derivation": s.derivation,
            }
            for s in sorted(unique.values(), key=lambda x: x.signature)
        ],
        "policy": {
            "mapping_frozen_before_market_outcomes": True,
            "inventory_testability_is_hard_gate": True,
            "opaque_rows_promoted_to_generic_proxy": False,
            "canonical_mechanism_is_not_exact_source_reproduction": True,
            "volume_required_scripts_excluded_from_independent_ohlc_lane": True,
            "protected_source_not_reverse_engineered": True,
            "script_accounting_reconciled": reconciled,
        },
    }
    if not reconciled:
        raise AssertionError("script accounting did not reconcile to frozen inventory")
    payload["semantic_sha256"] = B.digest(payload)
    return payload


def full_history_first_signals(
    frame: pd.DataFrame,
    symbol: str,
    spec: B.MechanismSpec,
) -> dict[str, tuple[pd.Timestamp, int]]:
    """Compute the indicator continuously on full symbol history, then pick first session hit.

    This prevents accidental daily EMA/SMA warm-up resets while retaining the one-signal-per-
    session contract. It remains causal because all indicator implementations are prefix-only.
    """
    result: dict[str, tuple[pd.Timestamp, int]] = {}
    source = (
        frame.loc[frame["symbol"].eq(symbol)]
        .sort_values("timestamp", kind="mergesort")
        .copy()
    )
    if source.empty:
        return result
    source["__signal"] = B._signal_for_family(source, spec).astype(int)
    for session, group in source.groupby("session_date", sort=True):
        hit = group.loc[group["__signal"].ne(0)]
        if hit.empty:
            continue
        row = hit.iloc[0]
        result[str(session)] = (pd.Timestamp(row["timestamp"]), int(row["__signal"]))
    return result


def guarded_holdout_test(
    frame: pd.DataFrame,
    specs: Sequence[B.MechanismSpec],
    outcomes: Mapping[str, Any],
    robust: Mapping[str, Any],
    symbol: str = "NIFTY",
) -> dict[str, Any]:
    """Score holdout only after robustness, with indicator warm-up from earlier history."""
    candidates = list(robust.get("survivor_hypothesis_ids", []))[: B.MAX_FINAL]
    if not candidates:
        return {"holdout_scored": False, "tested": [], "survivors": [], "results": []}

    record_by_id = {r["hypothesis_id"]: r for r in outcomes["records"]}
    spec_by_sig = {s.signature: s for s in specs}
    lookup = B.outcome_lookup(frame, symbol, {"holdout"})
    holdout_sessions = set(
        frame.loc[
            frame["symbol"].eq(symbol) & frame["split"].eq("holdout"),
            "session_date",
        ].astype(str)
    )
    results: list[dict[str, Any]] = []
    survivors: list[str] = []

    for hid in candidates:
        record = record_by_id[hid]
        spec = spec_by_sig[record["mechanism_signature"]]
        horizon = int(record["horizon_bars"])
        signals = full_history_first_signals(frame, symbol, spec)
        values: list[float] = []
        for session, (ts, direction) in signals.items():
            if session not in holdout_sessions:
                continue
            outcome = lookup.get((session, int(ts.value), horizon))
            if outcome is None:
                continue
            values.append(
                int(direction) * float(outcome["raw_return_bps"]) - B.A.COST_BPS
            )

        stats = B.summarize(values)
        gates = {
            "n_ge_15": stats["n"] >= 15,
            "mean_net_ge_2bps": float(stats["mean_bps"] or -1e9) >= 2.0,
            "hit_rate_ge_55pct": float(stats["hit_rate"] or 0.0) >= 0.55,
            "ci90_lower_positive": (
                stats["ci90"][0] is not None and float(stats["ci90"][0]) > 0.0
            ),
        }
        passed = all(gates.values())
        results.append(
            {
                "hypothesis_id": hid,
                "stats": stats,
                "gates": gates,
                "passed": passed,
            }
        )
        if passed:
            survivors.append(hid)

    return {
        "holdout_scored": True,
        "tested": candidates,
        "survivors": survivors,
        "results": results,
    }


def install() -> None:
    """Install the frozen-inventory and full-history guards into benchmark module globals."""
    B.prepare_specs = guarded_prepare_specs
    B.first_signals = full_history_first_signals
    B.holdout_test = guarded_holdout_test
