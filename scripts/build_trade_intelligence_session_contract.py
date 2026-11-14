from __future__ import annotations

from datetime import date, datetime, time, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import argparse
import gzip
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aixion_trade_intelligence.storage import atomic_write_json


IST = ZoneInfo("Asia/Kolkata")


class ContractBuildError(ValueError):
    pass


def _read_json(path: Path) -> Any:
    raw = path.read_bytes()
    try:
        if raw[:2] == b"\x1f\x8b":
            return json.loads(gzip.decompress(raw).decode("utf-8"))
        return json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractBuildError(f"cannot read JSON evidence {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _trade_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractBuildError("--trade-date must be YYYY-MM-DD") from exc


def _master_rows(path: Path) -> list[dict[str, Any]]:
    raw = _read_json(path)
    if not isinstance(raw, list):
        raise ContractBuildError("instrument master must be a JSON list")
    rows = [dict(row) for row in raw if isinstance(row, dict)]
    if not rows:
        raise ContractBuildError("instrument master contains no instrument objects")
    return rows


def _resolve_index(rows: list[dict[str, Any]], *, index_key: str, index_name: str) -> dict[str, Any]:
    if index_key:
        matches = [row for row in rows if str(row.get("instrument_key") or "") == index_key]
    else:
        matches = [
            row
            for row in rows
            if str(row.get("segment") or "") == "NSE_INDEX"
            and str(row.get("name") or "") == index_name
        ]
    if len(matches) != 1:
        descriptor = index_key or f"NSE_INDEX name={index_name!r}"
        raise ContractBuildError(f"expected exactly one index for {descriptor}; found {len(matches)}")
    return matches[0]


def _expiry_time(row: dict[str, Any]) -> datetime | None:
    raw = row.get("expiry")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    if value >= 1e14:
        value /= 1e6
    elif value >= 1e11:
        value /= 1e3
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _resolve_nearest_future(
    rows: list[dict[str, Any]],
    *,
    underlying_symbol: str,
    index_key: str,
    trade_date: date,
) -> dict[str, Any]:
    session_start = datetime.combine(trade_date, time.min, tzinfo=IST).astimezone(timezone.utc)
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    for row in rows:
        if str(row.get("segment") or "") != "NSE_FO":
            continue
        if str(row.get("instrument_type") or "").upper() != "FUT":
            continue
        row_symbol = str(
            row.get("underlying_symbol") or row.get("asset_symbol") or row.get("name") or ""
        )
        row_index_key = str(row.get("underlying_key") or row.get("asset_key") or "")
        if row_symbol != underlying_symbol and row_index_key != index_key:
            continue
        expiry = _expiry_time(row)
        if expiry is None or expiry < session_start:
            continue
        candidates.append((expiry, row))
    if not candidates:
        raise ContractBuildError(
            f"no non-expired NSE_FO future found for {underlying_symbol!r} / {index_key!r}"
        )
    candidates.sort(key=lambda item: (item[0], str(item[1].get("instrument_key") or "")))
    nearest_expiry = candidates[0][0]
    nearest = [row for expiry, row in candidates if expiry == nearest_expiry]
    if len(nearest) != 1:
        raise ContractBuildError(
            f"nearest future expiry is ambiguous: {[row.get('instrument_key') for row in nearest]}"
        )
    return nearest[0]


def _constituent_contract(path: Path | None) -> tuple[str, list[dict[str, Any]]]:
    if path is None:
        return "", []
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ContractBuildError("constituent weights file must be an object")
    version = str(raw.get("version") or "").strip()
    constituents = raw.get("constituents")
    if not version or not isinstance(constituents, list) or not constituents:
        raise ContractBuildError("constituent weights require version and non-empty constituents")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(constituents):
        if not isinstance(item, dict):
            raise ContractBuildError(f"constituents[{index}] must be an object")
        instrument = str(item.get("instrument_key") or "").strip()
        try:
            weight = float(item.get("weight"))
        except (TypeError, ValueError) as exc:
            raise ContractBuildError(f"constituents[{index}] has invalid weight") from exc
        if not instrument or weight <= 0 or weight != weight:
            raise ContractBuildError(f"constituents[{index}] requires exact key and positive weight")
        if instrument in seen:
            raise ContractBuildError(f"duplicate constituent {instrument}")
        seen.add(instrument)
        normalized.append({"instrument_key": instrument, "weight": weight})
    return version, normalized


def build_contract(
    *,
    instrument_master: Path,
    trade_date: date,
    index_key: str = "",
    index_name: str = "",
    underlying_symbol: str = "",
    include_nearest_future: bool = False,
    max_pair_lag_seconds: float | None = None,
    constituent_weights: Path | None = None,
    required_metrics: tuple[str, ...] = (),
    require_capture_instruments: bool = False,
) -> dict[str, Any]:
    if bool(index_key) == bool(index_name):
        raise ContractBuildError("provide exactly one of index_key or index_name")
    rows = _master_rows(instrument_master)
    index_row = _resolve_index(rows, index_key=index_key, index_name=index_name)
    resolved_index_key = str(index_row.get("instrument_key") or "")
    analytics: dict[str, Any] = {
        "index_instrument": resolved_index_key,
        "required_metrics": list(dict.fromkeys(required_metrics)),
        "instrument_master_sha256": _sha256(instrument_master),
        "instrument_master_file": instrument_master.name,
        "trade_date": trade_date.isoformat(),
    }
    expected = [resolved_index_key]
    if include_nearest_future:
        if not underlying_symbol:
            underlying_symbol = str(
                index_row.get("trading_symbol") or index_row.get("name") or ""
            ).strip()
        if max_pair_lag_seconds is None or max_pair_lag_seconds < 0:
            raise ContractBuildError(
                "--max-pair-lag-seconds must be supplied from the feed/SLA contract when future basis is requested"
            )
        future = _resolve_nearest_future(
            rows,
            underlying_symbol=underlying_symbol,
            index_key=resolved_index_key,
            trade_date=trade_date,
        )
        future_key = str(future.get("instrument_key") or "")
        analytics.update(
            {
                "futures_instrument": future_key,
                "futures_expiry": (
                    _expiry_time(future).isoformat().replace("+00:00", "Z")
                    if _expiry_time(future)
                    else ""
                ),
                "max_pair_lag_seconds": float(max_pair_lag_seconds),
            }
        )
        expected.append(future_key)

    weights_version, constituents = _constituent_contract(constituent_weights)
    if constituents:
        analytics["constituent_weights_version"] = weights_version
        analytics["constituents"] = constituents
        analytics["constituent_weights_sha256"] = _sha256(constituent_weights)
        expected.extend(item["instrument_key"] for item in constituents)

    contract: dict[str, Any] = {
        "contract_version": "1.0",
        "analytics_contract": analytics,
        "expected_event_types": ["MARKET_QUOTE"],
    }
    if require_capture_instruments:
        contract["expected_instruments"] = sorted(set(expected))
    return contract


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a point-in-time live intelligence session contract")
    parser.add_argument("--instrument-master", type=Path, required=True)
    parser.add_argument("--trade-date", required=True)
    index = parser.add_mutually_exclusive_group(required=True)
    index.add_argument("--index-key", default="")
    index.add_argument("--index-name", default="")
    parser.add_argument("--underlying-symbol", default="")
    parser.add_argument("--include-nearest-future", action="store_true")
    parser.add_argument("--max-pair-lag-seconds", type=float)
    parser.add_argument("--constituent-weights", type=Path)
    parser.add_argument("--required-metric", action="append", default=[])
    parser.add_argument("--require-capture-instruments", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = build_contract(
            instrument_master=args.instrument_master,
            trade_date=_trade_date(args.trade_date),
            index_key=args.index_key,
            index_name=args.index_name,
            underlying_symbol=args.underlying_symbol,
            include_nearest_future=args.include_nearest_future,
            max_pair_lag_seconds=args.max_pair_lag_seconds,
            constituent_weights=args.constituent_weights,
            required_metrics=tuple(args.required_metric),
            require_capture_instruments=args.require_capture_instruments,
        )
    except ContractBuildError as exc:
        raise SystemExit(str(exc)) from exc
    atomic_write_json(args.output, payload)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
