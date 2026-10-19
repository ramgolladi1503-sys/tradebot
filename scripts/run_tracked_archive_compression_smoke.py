#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

import pandas as pd
import pyarrow.parquet as pq

from research.option_e2e_recertification_v4.compression_breakout_option_campaign_v1 import (
    CompressionCampaignConfig,
    run_compression_campaign,
)


EXPECTED_ARCHIVE_SHA256 = (
    "4357f109ed631802b3774c34db9c318f71742f8e99de307408af71bf00810707"
)
SESSION_DIRECTORY = "20260709"
UNDERLYING = "NIFTY"
_OPTION_RE = re.compile(
    r"(?P<underlying>BANKNIFTY|NIFTY|SENSEX)"
    r".*?(?P<expiry>\d{1,2}[ _-]+[A-Z]{3}[ _-]+\d{2})"
    r".*?(?P<strike>\d{4,6}(?:\.\d+)?)"
    r"[ _-]+(?P<option_type>CE|PE)$",
    re.IGNORECASE,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ) + "\n"


def _write_json(path: Path, payload: object) -> str:
    content = _canonical(payload)
    path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )
    return digest


def _column_map(frame: pd.DataFrame) -> dict[str, str]:
    return {
        str(column).strip().lower().replace(" ", "_"): str(column)
        for column in frame.columns
    }


def _first_column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    mapping = _column_map(frame)
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _timestamps(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        numeric = pd.to_numeric(series, errors="coerce")
        median = float(numeric.dropna().abs().median()) if numeric.notna().any() else 0.0
        if median >= 1e17:
            parsed = pd.to_datetime(numeric, unit="ns", errors="coerce", utc=True)
        elif median >= 1e14:
            parsed = pd.to_datetime(numeric, unit="us", errors="coerce", utc=True)
        elif median >= 1e11:
            parsed = pd.to_datetime(numeric, unit="ms", errors="coerce", utc=True)
        else:
            parsed = pd.to_datetime(numeric, unit="s", errors="coerce", utc=True)
    else:
        parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().any():
        raise ValueError("invalid_archive_timestamp_rows")
    if getattr(parsed.dt, "tz", None) is None:
        return parsed.dt.tz_localize("Asia/Kolkata")
    return parsed.dt.tz_convert("Asia/Kolkata")


def _read_parquet_member(
    archive: zipfile.ZipFile,
    member: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    payload = archive.read(member)
    parquet = pq.ParquetFile(io.BytesIO(payload))
    metadata = {
        "member_path": member,
        "size_bytes": len(payload),
        "row_count": parquet.metadata.num_rows,
        "row_group_count": parquet.metadata.num_row_groups,
        "schema": [str(name) for name in parquet.schema_arrow.names],
    }
    return parquet.read().to_pandas(), metadata


def _normalize_ohlcv(
    frame: pd.DataFrame,
    *,
    symbol: str,
    contract_symbol: str | None = None,
) -> pd.DataFrame:
    timestamp_column = _first_column(frame, ("timestamp", "date", "datetime", "ts", "time"))
    if timestamp_column is None:
        raise ValueError(f"missing_timestamp_column:{symbol}")
    output = pd.DataFrame()
    output["timestamp"] = _timestamps(frame[timestamp_column])
    for target, aliases in {
        "open": ("open", "o"),
        "high": ("high", "h"),
        "low": ("low", "l"),
        "close": ("close", "c", "ltp"),
        "volume": ("volume", "vol", "v"),
    }.items():
        source = _first_column(frame, aliases)
        if source is None:
            if target == "volume":
                raise ValueError(f"missing_volume_column:{symbol}")
            raise ValueError(f"missing_{target}_column:{symbol}")
        output[target] = pd.to_numeric(frame[source], errors="coerce")
        if output[target].isna().any():
            raise ValueError(f"invalid_{target}_rows:{symbol}")
    if contract_symbol is None:
        output["symbol"] = symbol
    else:
        output["contract_symbol"] = contract_symbol
    return output.sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def _parse_option_member(member: str) -> dict[str, object] | None:
    stem = PurePosixPath(member).stem.upper()
    match = _OPTION_RE.search(stem)
    if match is None:
        return None
    expiry_text = re.sub(r"[ _-]+", " ", match.group("expiry")).title()
    expiry = pd.to_datetime(expiry_text, format="%d %b %y", errors="coerce")
    if pd.isna(expiry):
        return None
    return {
        "underlying": match.group("underlying").upper(),
        "option_type": match.group("option_type").upper(),
        "strike": float(match.group("strike")),
        "expiry": expiry.date().isoformat(),
        "contract_symbol": stem,
    }


def _select_underlying_member(members: list[str]) -> str:
    candidates = []
    for member in members:
        path = PurePosixPath(member)
        stem = path.stem.upper()
        if SESSION_DIRECTORY not in path.parts:
            continue
        if path.suffix.lower() != ".parquet":
            continue
        if stem == f"{UNDERLYING}_{SESSION_DIRECTORY}" or (
            stem.startswith(f"{UNDERLYING}_")
            and "BANKNIFTY" not in stem
            and "UNDERLYING" in member.upper()
        ):
            candidates.append(member)
    if len(candidates) != 1:
        raise ValueError(
            f"underlying_member_not_unique:{len(candidates)}:{candidates[:10]}"
        )
    return candidates[0]


def run_smoke(archive_path: Path) -> dict[str, object]:
    archive_hash = _sha256(archive_path)
    if archive_hash != EXPECTED_ARCHIVE_SHA256:
        raise ValueError(
            f"archive_hash_mismatch:{archive_hash}"
        )

    with zipfile.ZipFile(archive_path) as archive:
        members = sorted(
            info.filename
            for info in archive.infolist()
            if not info.is_dir()
            and not info.filename.startswith("__MACOSX/")
            and not PurePosixPath(info.filename).name.startswith("._")
        )
        underlying_member = _select_underlying_member(members)
        underlying_raw, underlying_meta = _read_parquet_member(
            archive, underlying_member
        )
        underlying_bars = _normalize_ohlcv(
            underlying_raw, symbol=UNDERLYING
        )

        option_metadata: list[dict[str, object]] = []
        option_frames: list[pd.DataFrame] = []
        catalog_rows: list[dict[str, object]] = []
        unparsed_option_members: list[str] = []
        for member in members:
            path = PurePosixPath(member)
            if SESSION_DIRECTORY not in path.parts or path.suffix.lower() != ".parquet":
                continue
            parsed = _parse_option_member(member)
            if parsed is None:
                stem = path.stem.upper()
                if re.search(r"(?:^|[ _-])(CE|PE)(?:$|[ _-])", stem):
                    unparsed_option_members.append(member)
                continue
            if parsed["underlying"] != UNDERLYING:
                continue
            raw, metadata = _read_parquet_member(archive, member)
            frame = _normalize_ohlcv(
                raw,
                symbol=str(parsed["contract_symbol"]),
                contract_symbol=str(parsed["contract_symbol"]),
            )
            option_frames.append(frame)
            option_metadata.append({**metadata, **parsed})
            catalog_rows.append(
                {
                    "session_date": "2026-07-09",
                    **parsed,
                }
            )

    if not option_frames:
        raise ValueError(
            "no_parseable_nifty_option_members:"
            + json.dumps(unparsed_option_members[:20])
        )
    option_bars = pd.concat(option_frames, ignore_index=True)
    catalog = pd.DataFrame(catalog_rows).drop_duplicates(
        ["session_date", "contract_symbol"], keep="first"
    )
    campaign = run_compression_campaign(
        underlying_bars=underlying_bars,
        contract_catalog=catalog,
        option_bars=option_bars,
        config=CompressionCampaignConfig(
            partition="smoke",
            minimum_trades=1,
            fixed_cost_per_order=20.0,
        ),
        source_dataset_hash=archive_hash,
    )

    status = "ARCHIVE_SCHEMA_AND_PIPELINE_SMOKE_PASS"
    if campaign.ledger.signals.empty:
        status = "ARCHIVE_SCHEMA_PASS_NO_COMPRESSION_SIGNAL"
    elif campaign.base_result is None or not campaign.base_result.trades:
        status = "ARCHIVE_SIGNAL_PASS_NO_OPTION_TRADE"

    return {
        "schema_version": "tracked_archive_compression_smoke_v1",
        "status": status,
        "archive_sha256": archive_hash,
        "session_date": "2026-07-09",
        "underlying": UNDERLYING,
        "underlying_member": underlying_member,
        "underlying_metadata": underlying_meta,
        "underlying_rows": len(underlying_bars),
        "option_member_count": len(option_metadata),
        "option_members": option_metadata,
        "unparsed_option_member_count": len(unparsed_option_members),
        "unparsed_option_members": unparsed_option_members,
        "catalog_contract_count": len(catalog),
        "signal_summary": campaign.ledger.summary,
        "campaign_summary": campaign.summary,
        "candle_summary": (
            campaign.base_result.summary
            if campaign.base_result is not None
            else None
        ),
        "sensitivity": campaign.sensitivity,
        "controls": campaign.controls,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "executable_option_pnl_certified": False,
        "coverage_verdict": "ONE_SESSION_SMOKE_ONLY",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Compression Breakout against the tracked 20260709 archive"
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("runtime/upstox_candidate_replay.zip"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    output = args.output_dir.expanduser().resolve(strict=False)
    output.mkdir(parents=True, exist_ok=True)
    result = run_smoke(args.archive.expanduser().resolve(strict=True))
    _write_json(output / "tracked_archive_compression_smoke.json", result)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
