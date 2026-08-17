#!/usr/bin/env python3
"""Post-close, read-only reconciliation of TradeBot subscription truth snapshots.

This verifier consumes JSON or JSONL artifacts already written by the frozen live
producer. It does not import broker/feed clients, does not mutate subscriptions,
and does not grant execution authority. Missing fields remain UNKNOWN rather
than being coerced to zero/false.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA = "tradebot-subscription-reconciliation-postclose-v1"


def _strict_loads(text: str) -> Any:
    def no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"JSON_DUPLICATE_KEY:{key}")
            out[key] = value
        return out

    return json.loads(text, object_pairs_hook=no_dupes)


def _normalize_tokens(value: Any) -> list[int] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple, set)):
        raise ValueError("TOKEN_LIST_INVALID")
    out: set[int] = set()
    for item in value:
        try:
            token = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError("TOKEN_VALUE_INVALID") from exc
        if token <= 0:
            raise ValueError("TOKEN_VALUE_INVALID")
        out.add(token)
    return sorted(out)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _rows_from_path(path: Path) -> list[dict[str, Any]]:
    resolved = path.expanduser().resolve()
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError(f"INPUT_REGULAR_FILE_REQUIRED:{resolved}")
    if resolved.suffix.lower() == ".json":
        payload = _strict_loads(resolved.read_text(encoding="utf-8"))
        if isinstance(payload, Mapping):
            return [dict(payload)]
        if isinstance(payload, list) and all(isinstance(row, Mapping) for row in payload):
            return [dict(row) for row in payload]
        raise ValueError("JSON_INPUT_MUST_BE_OBJECT_OR_OBJECT_LIST")
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(resolved.read_text(encoding="utf-8").splitlines(), start=1):
        text = raw.strip()
        if not text:
            continue
        payload = _strict_loads(text)
        if not isinstance(payload, Mapping):
            raise ValueError(f"JSONL_ROW_MUST_BE_OBJECT:{line_no}")
        rows.append(dict(payload))
    return rows


def _truth(row: Mapping[str, Any]) -> dict[str, Any]:
    intended = _normalize_tokens(row.get("intended_tokens"))
    subscribed = _normalize_tokens(row.get("subscribed_tokens"))
    declared_missing = _normalize_tokens(row.get("missing_tokens"))
    declared_extra = _normalize_tokens(row.get("extra_tokens"))
    pending_sub = _normalize_tokens(row.get("pending_subscribe_tokens"))
    pending_unsub = _normalize_tokens(row.get("pending_unsubscribe_tokens"))
    pending_mode = _normalize_tokens(row.get("pending_mode_full_tokens"))

    if intended is None or subscribed is None:
        derived_missing = None
        derived_extra = None
        set_consistent = None
    else:
        derived_missing = sorted(set(intended) - set(subscribed))
        derived_extra = sorted(set(subscribed) - set(intended))
        set_consistent = not derived_missing and not derived_extra
        if declared_missing is not None and declared_missing != derived_missing:
            raise ValueError("DECLARED_MISSING_TOKENS_MISMATCH")
        if declared_extra is not None and declared_extra != derived_extra:
            raise ValueError("DECLARED_EXTRA_TOKENS_MISMATCH")

    pending_known = pending_sub is not None and pending_unsub is not None and pending_mode is not None
    pending_clear = (
        not pending_sub and not pending_unsub and not pending_mode
        if pending_known
        else None
    )
    derived_registry_consistent = (
        bool(set_consistent and pending_clear)
        if set_consistent is not None and pending_clear is not None and intended
        else None
    )
    declared_registry = row.get("subscription_registry_consistent")
    if declared_registry is not None and derived_registry_consistent is not None:
        if bool(declared_registry) != bool(derived_registry_consistent):
            raise ValueError("DECLARED_REGISTRY_CONSISTENCY_MISMATCH")

    return {
        "ts_epoch": _float(row.get("ts_epoch") or row.get("timestamp_epoch") or row.get("receipt_epoch")),
        "run_id": str(row.get("run_id") or "").strip() or None,
        "feed_session_id": str(row.get("feed_session_id") or "").strip() or None,
        "runtime_state": str(row.get("runtime_state") or "").strip().upper() or None,
        "feed_truth_state": str(row.get("feed_truth_state") or "").strip().upper() or None,
        "intended_tokens": intended,
        "subscribed_tokens": subscribed,
        "missing_tokens": derived_missing if derived_missing is not None else declared_missing,
        "extra_tokens": derived_extra if derived_extra is not None else declared_extra,
        "pending_subscribe_tokens": pending_sub,
        "pending_unsubscribe_tokens": pending_unsub,
        "pending_mode_full_tokens": pending_mode,
        "subscription_registry_consistent": derived_registry_consistent if derived_registry_consistent is not None else declared_registry,
    }


def reconcile(paths: Iterable[Path]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(_rows_from_path(path))
    if not rows:
        raise ValueError("NO_SNAPSHOT_ROWS")

    truth_rows = [_truth(row) for row in rows]
    indexed = list(enumerate(truth_rows))
    indexed.sort(key=lambda pair: (pair[1]["ts_epoch"] is None, pair[1]["ts_epoch"] or float("inf"), pair[0]))
    ordered = [row for _, row in indexed]

    known_times = [row["ts_epoch"] for row in ordered if row["ts_epoch"] is not None]
    time_monotonic = all(a <= b for a, b in zip(known_times, known_times[1:]))
    if not time_monotonic:
        raise ValueError("SNAPSHOT_TIME_NON_MONOTONIC")

    run_ids = sorted({row["run_id"] for row in ordered if row["run_id"]})
    session_ids = sorted({row["feed_session_id"] for row in ordered if row["feed_session_id"]})
    identity_consistent = len(run_ids) <= 1 and len(session_ids) <= 1

    inconsistent_rows = [row for row in ordered if row["subscription_registry_consistent"] is False]
    unknown_rows = [row for row in ordered if row["subscription_registry_consistent"] is None]
    consistent_rows = [row for row in ordered if row["subscription_registry_consistent"] is True]

    max_missing = max((len(row["missing_tokens"] or []) for row in ordered if row["missing_tokens"] is not None), default=None)
    max_extra = max((len(row["extra_tokens"] or []) for row in ordered if row["extra_tokens"] is not None), default=None)
    max_pending = max(
        (
            len(row["pending_subscribe_tokens"] or [])
            + len(row["pending_unsubscribe_tokens"] or [])
            + len(row["pending_mode_full_tokens"] or [])
            for row in ordered
            if row["pending_subscribe_tokens"] is not None
            and row["pending_unsubscribe_tokens"] is not None
            and row["pending_mode_full_tokens"] is not None
        ),
        default=None,
    )

    divergence_windows: list[dict[str, Any]] = []
    current_start: float | None = None
    current_rows = 0
    for row in ordered:
        bad = row["subscription_registry_consistent"] is False
        if bad and current_rows == 0:
            current_start = row["ts_epoch"]
        if bad:
            current_rows += 1
            continue
        if current_rows:
            divergence_windows.append({"start_ts_epoch": current_start, "end_ts_epoch": row["ts_epoch"], "rows": current_rows})
            current_start = None
            current_rows = 0
    if current_rows:
        divergence_windows.append({"start_ts_epoch": current_start, "end_ts_epoch": None, "rows": current_rows})

    final = ordered[-1]
    final_consistent = final["subscription_registry_consistent"] is True
    fully_known = not unknown_rows and all(row["ts_epoch"] is not None for row in ordered)

    if not identity_consistent:
        verdict = "FAIL_IDENTITY_DRIFT"
    elif inconsistent_rows:
        verdict = "FAIL_SUBSCRIPTION_DIVERGENCE"
    elif unknown_rows:
        verdict = "UNKNOWN_INCOMPLETE_SUBSCRIPTION_TRUTH"
    elif not final_consistent:
        verdict = "FAIL_FINAL_SUBSCRIPTION_STATE"
    else:
        verdict = "PASS_POSTCLOSE_RECONCILIATION"

    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "snapshot_rows": len(ordered),
        "consistent_rows": len(consistent_rows),
        "inconsistent_rows": len(inconsistent_rows),
        "unknown_rows": len(unknown_rows),
        "identity_consistent": identity_consistent,
        "run_ids": run_ids,
        "feed_session_ids": session_ids,
        "fully_known": fully_known,
        "final_subscription_registry_consistent": final_consistent,
        "max_missing_tokens": max_missing,
        "max_extra_tokens": max_extra,
        "max_pending_token_operations": max_pending,
        "divergence_windows": divergence_windows,
        "final_snapshot": final,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "structural_edge_certified": False,
        "interpretation": "PASS means only that observed producer subscription registries reconciled in supplied snapshots; it is not proof of tick freshness, complete exchange delivery, feed recovery, execution viability, or edge.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = reconcile(args.inputs)
    text = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        target = args.output.expanduser().absolute()
        if target.exists():
            raise ValueError("OUTPUT_ALREADY_EXISTS")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["verdict"] == "PASS_POSTCLOSE_RECONCILIATION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
