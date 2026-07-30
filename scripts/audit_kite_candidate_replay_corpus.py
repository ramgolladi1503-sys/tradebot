from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

UNDERLYING_PATTERN = re.compile(r"^(NIFTY|BANKNIFTY|SENSEX)_(\d{4}-\d{2}-\d{2})\.parquet$")
REQUIRED_COLUMNS = {
    "date", "open", "high", "low", "close", "volume", "instrument",
    "interval", "source", "synthetic", "fallback", "mock", "fetch_date",
}
EXPECTED_INSTRUMENTS = {"NIFTY", "BANKNIFTY", "SENSEX"}


@dataclass(frozen=True)
class FileAudit:
    path: str
    instrument: str
    session: str
    rows: int
    schema_ok: bool
    timestamps_monotonic: bool
    duplicate_timestamps: int
    nonpositive_prices: int
    invalid_ohlc_rows: int
    synthetic_rows: int
    fallback_rows: int
    mock_rows: int
    source_values: tuple[str, ...]
    interval_values: tuple[str, ...]
    first_timestamp: str | None
    last_timestamp: str | None
    sha256: str
    error: str | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bool_count(frame: pd.DataFrame, column: str) -> int:
    if column not in frame:
        return 0
    return int(frame[column].fillna(False).astype(bool).sum())


def audit_underlying_file(path: Path, instrument: str, session: str) -> FileAudit:
    try:
        frame = pd.read_parquet(path)
        schema_ok = REQUIRED_COLUMNS.issubset(frame.columns)
        timestamps = pd.to_datetime(frame.get("date"), utc=True, errors="coerce")
        prices = frame.reindex(columns=["open", "high", "low", "close"]).apply(
            pd.to_numeric, errors="coerce"
        )
        invalid_ohlc = (
            prices.isna().any(axis=1)
            | (prices["high"] < prices[["open", "close", "low"]].max(axis=1))
            | (prices["low"] > prices[["open", "close", "high"]].min(axis=1))
        )
        return FileAudit(
            path=str(path),
            instrument=instrument,
            session=session,
            rows=int(len(frame)),
            schema_ok=bool(schema_ok),
            timestamps_monotonic=bool(timestamps.notna().all() and timestamps.is_monotonic_increasing),
            duplicate_timestamps=int(timestamps.duplicated().sum()),
            nonpositive_prices=int((prices <= 0).any(axis=1).sum()),
            invalid_ohlc_rows=int(invalid_ohlc.sum()),
            synthetic_rows=_bool_count(frame, "synthetic"),
            fallback_rows=_bool_count(frame, "fallback"),
            mock_rows=_bool_count(frame, "mock"),
            source_values=tuple(sorted(str(v) for v in frame.get("source", pd.Series(dtype=object)).dropna().unique())),
            interval_values=tuple(sorted(str(v) for v in frame.get("interval", pd.Series(dtype=object)).dropna().unique())),
            first_timestamp=None if timestamps.empty or timestamps.isna().all() else timestamps.min().isoformat(),
            last_timestamp=None if timestamps.empty or timestamps.isna().all() else timestamps.max().isoformat(),
            sha256=_sha256(path),
        )
    except Exception as exc:
        return FileAudit(
            path=str(path), instrument=instrument, session=session, rows=0,
            schema_ok=False, timestamps_monotonic=False, duplicate_timestamps=0,
            nonpositive_prices=0, invalid_ohlc_rows=0, synthetic_rows=0,
            fallback_rows=0, mock_rows=0, source_values=(), interval_values=(),
            first_timestamp=None, last_timestamp=None, sha256=_sha256(path), error=repr(exc),
        )


def run_audit(root: Path) -> dict[str, Any]:
    underlying: list[tuple[Path, str, str]] = []
    option_files: list[Path] = []
    for path in sorted(root.rglob("*.parquet")):
        match = UNDERLYING_PATTERN.match(path.name)
        if match:
            underlying.append((path, match.group(1), match.group(2)))
        elif "/options/" in path.as_posix():
            option_files.append(path)

    audits = [audit_underlying_file(*item) for item in underlying]
    sessions: dict[str, set[str]] = {}
    for _, instrument, session in underlying:
        sessions.setdefault(session, set()).add(instrument)
    incomplete = {
        session: sorted(EXPECTED_INSTRUMENTS - instruments)
        for session, instruments in sessions.items()
        if instruments != EXPECTED_INSTRUMENTS
    }
    option_mock_named = [path for path in option_files if "MOCK" in path.name.upper()]

    defects = {
        "load_errors": sum(a.error is not None for a in audits),
        "schema_failures": sum(not a.schema_ok for a in audits),
        "nonmonotonic_files": sum(not a.timestamps_monotonic for a in audits),
        "duplicate_timestamps": sum(a.duplicate_timestamps for a in audits),
        "nonpositive_price_rows": sum(a.nonpositive_prices for a in audits),
        "invalid_ohlc_rows": sum(a.invalid_ohlc_rows for a in audits),
        "synthetic_rows": sum(a.synthetic_rows for a in audits),
        "fallback_rows": sum(a.fallback_rows for a in audits),
        "mock_underlying_rows": sum(a.mock_rows for a in audits),
        "incomplete_sessions": len(incomplete),
    }
    underlying_trusted = bool(audits) and not any(defects.values())
    options_trusted = bool(option_files) and not option_mock_named

    return {
        "root": str(root),
        "underlying_file_count": len(underlying),
        "session_count": len(sessions),
        "session_start": min(sessions) if sessions else None,
        "session_end": max(sessions) if sessions else None,
        "instrument_file_counts": dict(Counter(i for _, i, _ in underlying)),
        "incomplete_sessions": incomplete,
        "option_file_count": len(option_files),
        "mock_named_option_file_count": len(option_mock_named),
        "mock_named_option_files": [str(path) for path in option_mock_named],
        "defects": defects,
        "verdict": {
            "underlying_discovery_eligible": underlying_trusted,
            "option_profitability_validation_eligible": options_trusted,
            "mock_options_must_not_certify_strategy": bool(option_mock_named),
        },
        "files": [asdict(audit) for audit in audits],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/kite_replay_corpus_audit.json"))
    parser.add_argument("--require-trusted-underlying", action="store_true")
    args = parser.parse_args()
    report = run_audit(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report["verdict"], sort_keys=True))
    return 0 if not args.require_trusted_underlying or report["verdict"]["underlying_discovery_eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
