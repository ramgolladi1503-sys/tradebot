from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "docs" / "agent_reviews" / "four_strategy_dataset_manifest_v3.json"
CANONICAL_INVENTORY_PATH = PROJECT_ROOT / "docs" / "agent_reviews" / "upstox_corpus_inventory_v2.json"
CANONICAL_INVENTORY_SIDECAR_PATH = PROJECT_ROOT / "docs" / "agent_reviews" / "upstox_corpus_inventory_v2.json.sha256"
SUPPORTED_SESSION_SUFFIXES = (".parquet", ".csv", ".json", ".jsonl")
ALLOWED_SYMBOLS = frozenset({"NIFTY", "BANKNIFTY", "SENSEX"})
EXPECTED_SESSION_ROWS = 375
SUPPORTED_INVENTORY_SCHEMA_VERSIONS = frozenset({1})
PROJECTED_SESSION_COLUMNS = (
    "timestamp",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


class ReplaySourceSelectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class InventoryResolution:
    original_provenance_path: str
    resolved_runtime_path: str
    inventory_sha256: str
    manifest_expected_inventory_sha256: str | None
    sidecar_sha256: str
    sidecar_verified: bool
    schema_version: int
    resolution_mode: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_provenance_path": self.original_provenance_path,
            "resolved_runtime_path": self.resolved_runtime_path,
            "inventory_sha256": self.inventory_sha256,
            "manifest_expected_inventory_sha256": self.manifest_expected_inventory_sha256,
            "sidecar_sha256": self.sidecar_sha256,
            "sidecar_verified": self.sidecar_verified,
            "schema_version": self.schema_version,
            "resolution_mode": self.resolution_mode,
        }


@dataclass(frozen=True)
class SessionFileRecord:
    absolute_path: str
    logical_path: str
    symbol: str
    session_date: str
    source_root: str
    sha256: str
    row_count: int
    byte_size: int
    projected_columns: tuple[str, ...]
    selected_via: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "absolute_path": self.absolute_path,
            "logical_path": self.logical_path,
            "symbol": self.symbol,
            "session_date": self.session_date,
            "source_root": self.source_root,
            "sha256": self.sha256,
            "row_count": self.row_count,
            "byte_size": self.byte_size,
            "projected_columns": list(self.projected_columns),
            "selected_via": self.selected_via,
        }


@dataclass(frozen=True)
class SessionLoadResult:
    bars: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_underlying_symbol(raw_symbol: Any) -> str | None:
    text = str(raw_symbol or "").strip().upper()
    if not text:
        return None
    if "BANKNIFTY" in text or "NIFTY BANK" in text or "BANK NIFTY" in text or "NIFTYBANK" in text:
        return "BANKNIFTY"
    if "NIFTY" in text and "BANKNIFTY" not in text:
        return "NIFTY"
    if "SENSEX" in text:
        return "SENSEX"
    return None


def load_manifest_payload(manifest_path: Path | str | None = None) -> dict[str, Any]:
    path = Path(manifest_path or DEFAULT_MANIFEST_PATH)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReplaySourceSelectionError(f"manifest_json_malformed:{path}") from exc


def _infer_project_root_from_manifest_path(manifest_path: Path | str | None) -> Path:
    path = Path(manifest_path or DEFAULT_MANIFEST_PATH).resolve()
    if path.parent.name == "agent_reviews" and path.parent.parent.name == "docs":
        return path.parents[2]
    return path.parent


def approved_source_roots(manifest: dict[str, Any]) -> tuple[Path, ...]:
    roots = manifest.get("requested_source_roots") or manifest.get("source_roots") or []
    out = tuple(Path(str(root)).expanduser() for root in roots if str(root or "").strip())
    if not out:
        raise ReplaySourceSelectionError("missing_authoritative_source_roots")
    for root in out:
        if not root.exists():
            raise ReplaySourceSelectionError(f"authoritative_root_unavailable:{root}")
    return out


def manifest_selected_underlyings(manifest: dict[str, Any], *, strategy_id: str) -> tuple[str, ...]:
    values = sorted(
        {
            str(entry.get("underlying_identity")).strip().upper()
            for entry in (manifest.get("composite_corpora") or [])
            if str(entry.get("strategy_id")).strip() == strategy_id and str(entry.get("underlying_identity") or "").strip()
        }
    )
    if not values:
        raise ReplaySourceSelectionError(f"missing_manifest_composites:{strategy_id}")
    unsupported = [value for value in values if value not in ALLOWED_SYMBOLS]
    if unsupported:
        raise ReplaySourceSelectionError(f"unsupported_manifest_underlyings:{','.join(unsupported)}")
    return tuple(values)


def _read_sidecar_sha256(path: Path) -> str:
    if not path.exists():
        raise ReplaySourceSelectionError(f"inventory_sidecar_missing:{path}")
    expected = str(path.read_text(encoding="utf-8").split()[0]).strip().lower()
    if len(expected) != 64:
        raise ReplaySourceSelectionError(f"inventory_sidecar_malformed:{path}")
    return expected


def resolve_inventory_artifact(
    manifest: dict[str, Any],
    *,
    project_root: Path | None = None,
) -> InventoryResolution:
    project_root = project_root or PROJECT_ROOT
    provenance_path = str(manifest.get("inventory_path") or "").strip()
    manifest_expected_hash = str(manifest.get("inventory_sha256") or "").strip().lower() or None
    canonical_path = project_root / "docs" / "agent_reviews" / "upstox_corpus_inventory_v2.json"
    canonical_sidecar = canonical_path.with_suffix(canonical_path.suffix + ".sha256")

    candidate_path: Path
    resolution_mode: str
    if provenance_path:
        provenance_candidate = Path(provenance_path).expanduser()
        if provenance_candidate.exists():
            candidate_path = provenance_candidate
            resolution_mode = "manifest_provenance_path"
        else:
            candidate_path = canonical_path
            resolution_mode = "repo_relative_canonical"
    else:
        candidate_path = canonical_path
        resolution_mode = "repo_relative_canonical"

    if not candidate_path.exists():
        raise ReplaySourceSelectionError(f"inventory_path_unavailable:{candidate_path}")
    if candidate_path.resolve() == canonical_path.resolve():
        sidecar_path = canonical_sidecar
    else:
        sidecar_path = candidate_path.with_suffix(candidate_path.suffix + ".sha256")
    sidecar_sha = _read_sidecar_sha256(sidecar_path)
    actual_sha = sha256_file(candidate_path)
    if sidecar_sha != actual_sha:
        raise ReplaySourceSelectionError(
            f"inventory_sidecar_hash_mismatch:{candidate_path}:expected={sidecar_sha}:actual={actual_sha}"
        )
    if manifest_expected_hash is not None and manifest_expected_hash != actual_sha:
        raise ReplaySourceSelectionError(
            f"inventory_manifest_hash_mismatch:{candidate_path}:expected={manifest_expected_hash}:actual={actual_sha}"
        )
    try:
        payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReplaySourceSelectionError(f"inventory_json_malformed:{candidate_path}") from exc
    schema_version = int(payload.get("schema_version") or 0)
    if schema_version not in SUPPORTED_INVENTORY_SCHEMA_VERSIONS:
        raise ReplaySourceSelectionError(f"inventory_schema_unsupported:{schema_version}")
    return InventoryResolution(
        original_provenance_path=provenance_path,
        resolved_runtime_path=str(candidate_path.resolve()),
        inventory_sha256=actual_sha,
        manifest_expected_inventory_sha256=manifest_expected_hash,
        sidecar_sha256=sidecar_sha,
        sidecar_verified=True,
        schema_version=schema_version,
        resolution_mode=resolution_mode,
        payload=payload,
    )


def _file_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    files = payload.get("files") or {}
    if not isinstance(files, dict):
        raise ReplaySourceSelectionError("inventory_files_not_mapping")
    return [dict(row) for row in files.values()]


def _file_session_date(row: dict[str, Any]) -> str:
    timestamp_min = str(row.get("timestamp_min") or "").strip()
    if timestamp_min:
        return timestamp_min[:10]
    logical_name = Path(str(row.get("logical_path") or "")).stem
    if "_" in logical_name:
        suffix = logical_name.rsplit("_", 1)[-1]
        if len(suffix) == 8 and suffix.isdigit():
            return f"{suffix[:4]}-{suffix[4:6]}-{suffix[6:8]}"
    raise ReplaySourceSelectionError(f"inventory_session_date_missing:{row.get('logical_path')}")


def _select_from_inventory(
    resolution: InventoryResolution,
    *,
    underlyings: set[str],
    approved_roots: tuple[Path, ...],
    max_records: int | None = None,
) -> list[SessionFileRecord]:
    selected: list[SessionFileRecord] = []
    for row in _file_records(resolution.payload):
        if str(row.get("data_role")).strip() != "UNDERLYING_CANDLES":
            continue
        if str(row.get("quality_status")).strip() != "ACCEPTED":
            continue
        if str(row.get("session_status")).strip() != "FULL_SESSION":
            continue
        symbol_values = row.get("symbol_values") or []
        normalized = {normalize_underlying_symbol(value) for value in symbol_values}
        symbol = next((item for item in normalized if item in underlyings), None)
        if symbol is None:
            continue
        path = Path(str(row.get("absolute_path") or "")).expanduser()
        if not path.exists():
            raise ReplaySourceSelectionError(f"inventory_selected_source_missing:{path}")
        if not any(str(path).startswith(str(root)) for root in approved_roots):
            raise ReplaySourceSelectionError(f"selected_path_outside_authority:{path}")
        inventory_sha = str(row.get("sha256") or "").strip().lower()
        if not inventory_sha:
            raise ReplaySourceSelectionError(f"inventory_source_hash_missing:{path}")
        if sha256_file(path) != inventory_sha:
            raise ReplaySourceSelectionError(f"inventory_source_hash_mismatch:{path}")
        selected.append(
            SessionFileRecord(
                absolute_path=str(path.resolve()),
                logical_path=str(row.get("logical_path") or ""),
                symbol=symbol,
                session_date=_file_session_date(row),
                source_root=str(row.get("source_root") or ""),
                sha256=inventory_sha,
                row_count=int(row.get("row_count") or 0),
                byte_size=int(row.get("byte_size") or 0),
                projected_columns=PROJECTED_SESSION_COLUMNS,
                selected_via="inventory_verified_repo_relative",
            )
        )
        if max_records is not None and len(selected) >= max_records:
            break
    selected = sorted(selected, key=lambda item: (item.symbol, item.session_date, item.logical_path))
    if max_records is not None:
        selected = selected[:max_records]
    return selected


def _read_frame(path: Path, *, projected_columns: tuple[str, ...] = PROJECTED_SESSION_COLUMNS) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path, columns=list(projected_columns))
    if suffix == ".csv":
        return pd.read_csv(path, usecols=list(projected_columns))
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    raise ReplaySourceSelectionError(f"unsupported_session_file:{path}")


def read_session_bars(
    path: Path,
    *,
    projected_columns: tuple[str, ...] = PROJECTED_SESSION_COLUMNS,
) -> SessionLoadResult:
    read_started = perf_counter()
    frame = _read_frame(path, projected_columns=projected_columns)
    read_elapsed = perf_counter() - read_started
    normalize_started = perf_counter()
    if "timestamp" not in frame.columns:
        raise ReplaySourceSelectionError(f"missing_timestamp_column:{path}")
    missing = {"open", "high", "low", "close", "symbol"} - set(map(str, frame.columns))
    if missing:
        raise ReplaySourceSelectionError(f"missing_required_columns:{path}:{','.join(sorted(missing))}")
    timestamp = pd.to_datetime(frame["timestamp"], errors="coerce")
    if timestamp.isna().any():
        raise ReplaySourceSelectionError(f"invalid_timestamp_values:{path}")
    if any(timestamp.iloc[idx] <= timestamp.iloc[idx - 1] for idx in range(1, len(timestamp))):
        raise ReplaySourceSelectionError(f"non_monotonic_timestamps:{path}")
    minute_delta = timestamp.diff().dropna().dt.total_seconds()
    if not minute_delta.empty and not (minute_delta == 60).all():
        raise ReplaySourceSelectionError(f"non_one_minute_cadence:{path}")
    session_date = timestamp.iloc[0].date().isoformat()
    starts = timestamp.dt.tz_localize("Asia/Kolkata") if timestamp.dt.tz is None else timestamp.dt.tz_convert("Asia/Kolkata")
    symbol = normalize_underlying_symbol(frame["symbol"].iloc[0])
    if symbol is None:
        raise ReplaySourceSelectionError(f"unsupported_symbol:{path}")
    values: list[dict[str, Any]] = []
    volume_present = "volume" in frame.columns
    for row in frame.itertuples(index=False):
        row_map = row._asdict()
        start = starts.iloc[len(values)]
        end = start + pd.Timedelta(minutes=1)
        open_price = float(row_map["open"])
        high_price = float(row_map["high"])
        low_price = float(row_map["low"])
        close_price = float(row_map["close"])
        if min(open_price, high_price, low_price, close_price) <= 0:
            raise ReplaySourceSelectionError(f"non_positive_price:{path}")
        if high_price < max(open_price, close_price, low_price):
            raise ReplaySourceSelectionError(f"invalid_ohlc_high:{path}")
        if low_price > min(open_price, close_price, high_price):
            raise ReplaySourceSelectionError(f"invalid_ohlc_low:{path}")
        volume = None
        if volume_present and pd.notna(row_map.get("volume")):
            volume = float(row_map["volume"])
        values.append(
            {
                "symbol": symbol,
                "session_date": session_date,
                "timeframe": "1m",
                "bar_start_timestamp": start.isoformat(),
                "bar_end_timestamp": end.isoformat(),
                "ts": start.isoformat(),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
                "is_complete": True,
                "source": "upstox_candidate_replay",
                "source_timestamp": end.isoformat(),
                "receipt_timestamp": end.isoformat(),
            }
        )
    if len(values) != EXPECTED_SESSION_ROWS:
        raise ReplaySourceSelectionError(f"unexpected_session_row_count:{path}:{len(values)}")
    first_ts = values[0]["bar_start_timestamp"]
    last_end = values[-1]["bar_end_timestamp"]
    if not str(first_ts).endswith("09:15:00+05:30"):
        raise ReplaySourceSelectionError(f"session_open_mismatch:{path}:{first_ts}")
    if not str(last_end).endswith("15:30:00+05:30"):
        raise ReplaySourceSelectionError(f"session_close_mismatch:{path}:{last_end}")
    normalize_elapsed = perf_counter() - normalize_started
    return SessionLoadResult(
        bars=tuple(values),
        metrics={
            "path": str(path),
            "file_size_bytes": path.stat().st_size,
            "projected_columns": list(projected_columns),
            "rows_loaded": len(values),
            "read_seconds": read_elapsed,
            "normalization_seconds": normalize_elapsed,
        },
    )


def _fallback_select_by_scan(
    *,
    approved_roots: tuple[Path, ...],
    underlyings: set[str],
    max_records: int | None = None,
) -> list[SessionFileRecord]:
    selected: list[SessionFileRecord] = []
    for root in approved_roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SESSION_SUFFIXES:
                continue
            if "underlying" not in {part.lower() for part in path.parts}:
                continue
            try:
                loaded = read_session_bars(path)
            except Exception:
                continue
            symbol = str(loaded.bars[0]["symbol"])
            if symbol not in underlyings:
                continue
            selected.append(
                SessionFileRecord(
                    absolute_path=str(path.resolve()),
                    logical_path=str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else str(path.name),
                    symbol=symbol,
                    session_date=str(loaded.bars[0]["session_date"]),
                    source_root=str(root.resolve()),
                    sha256=sha256_file(path),
                    row_count=len(loaded.bars),
                    byte_size=path.stat().st_size,
                    projected_columns=PROJECTED_SESSION_COLUMNS,
                    selected_via="diagnostic_root_scan",
                )
            )
            if max_records is not None and len(selected) >= max_records:
                return sorted(selected, key=lambda item: (item.symbol, item.session_date, item.logical_path))
    return sorted(selected, key=lambda item: (item.symbol, item.session_date, item.logical_path))


def select_session_files(
    *,
    manifest_path: Path | str | None = None,
    strategy_id: str,
    require_inventory: bool = True,
    max_records: int | None = None,
) -> tuple[InventoryResolution | None, list[SessionFileRecord]]:
    manifest = load_manifest_payload(manifest_path)
    project_root = _infer_project_root_from_manifest_path(manifest_path)
    roots = approved_source_roots(manifest)
    underlyings = set(manifest_selected_underlyings(manifest, strategy_id=strategy_id))
    try:
        resolution = resolve_inventory_artifact(manifest, project_root=project_root)
    except ReplaySourceSelectionError:
        if require_inventory:
            raise
        selected = _fallback_select_by_scan(approved_roots=roots, underlyings=underlyings, max_records=max_records)
        if not selected:
            raise ReplaySourceSelectionError("fallback_selected_zero_sessions")
        return None, selected
    selected = _select_from_inventory(resolution, underlyings=underlyings, approved_roots=roots, max_records=max_records)
    if not selected:
        raise ReplaySourceSelectionError("inventory_selected_zero_sessions")
    return resolution, selected


def selection_summary(records: Iterable[SessionFileRecord]) -> dict[str, Any]:
    rows = list(records)
    by_symbol = Counter(record.symbol for record in rows)
    return {
        "selected_file_count": len(rows),
        "symbol_counts": dict(sorted(by_symbol.items())),
        "earliest_session": min((record.session_date for record in rows), default=None),
        "latest_session": max((record.session_date for record in rows), default=None),
        "selected_via": dict(sorted(Counter(record.selected_via for record in rows).items())),
        "projected_columns": list(PROJECTED_SESSION_COLUMNS),
        "semantic_hash": hashlib.sha256(
            canonical_json_bytes([record.to_dict() for record in rows])
        ).hexdigest(),
    }
